"""Cross-message aggregation helpers for behavioural-analysis case patterns."""
# pylint: disable=too-many-arguments,too-many-branches,too-many-locals

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any, Literal, TypedDict

from ._utils import _as_dict, _compact

CASE_PATTERN_VERSION = "1"
_EVENT_BEHAVIOR_MAP: dict[str, str] = {
    "deadline_pressure": "deadline_pressure",
    "escalation": "escalation",
    "exclusion_or_omission": "selective_accountability",
    "comparator_treatment": "selective_accountability",
}

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


def _parse_datetime(value: str) -> datetime | None:
    """Return one parsed datetime or None for invalid inputs."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _date_key(value: str) -> tuple[int, str]:
    """Return a sortable date key tolerant of partial or invalid inputs."""
    if not value:
        return (1, "")
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(UTC).replace(tzinfo=None)
        return (0, parsed.isoformat())
    except ValueError:
        return (0, value)


def _ordered_unique(values: list[str]) -> list[str]:
    """Return ordered unique strings, skipping empties."""
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = _compact(value)
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


def _event_rows(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Return non-quoted, non-forwarded event records from candidate."""
    rows = [item for item in candidate.get("event_records", []) if isinstance(item, dict)]
    if not rows:
        return []
    return [row for row in rows if str(row.get("source_scope") or "") not in {"quoted_body", "forwarded_header"}]


def _event_behavior_ids(candidate: dict[str, Any]) -> set[str]:
    """Extract behavior IDs from event rows in candidate using event-to-behavior mapping."""
    derived: set[str] = set()
    for row in _event_rows(candidate):
        event_kind = str(row.get("event_kind") or "")
        behavior_id = _EVENT_BEHAVIOR_MAP.get(event_kind)
        if behavior_id:
            derived.add(behavior_id)
    return derived


def _event_kind_ids(candidate: dict[str, Any]) -> list[str]:
    """Return ordered unique event kind IDs from candidate event rows."""
    return _ordered_unique(
        [str(row.get("event_kind") or "") for row in _event_rows(candidate) if str(row.get("event_kind") or "")]
    )


def _event_confidence_score(candidate: dict[str, Any]) -> int:
    """Return the maximum confidence score from event rows in candidate."""
    return max([_confidence_score(str(row.get("confidence") or "")) for row in _event_rows(candidate)] or [0])


def _authored_findings(candidate: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(_as_dict(candidate.get("message_findings")).get("authored_text"))


def _behavior_ids(candidate: dict[str, Any]) -> set[str]:
    return {
        str(item.get("behavior_id") or "")
        for item in _authored_findings(candidate).get("behavior_candidates", [])
        if isinstance(item, dict)
    }


def _primary_recurrence(
    *,
    message_count: int,
    actor_count: int,
    thread_count: int,
    target_actor_id: str,
    target_linked_count: int,
    sender_actor_ids: list[str],
    dated_rows: list[dict[str, Any]],
) -> tuple[RecurrenceLabel, list[RecurrenceLabel]]:
    """Return a conservative recurrence classification with supporting flags."""
    if message_count == 1:
        return "isolated", []
    flags = _recurrence_flags(message_count, actor_count, thread_count, target_actor_id, target_linked_count, sender_actor_ids)
    confidence_trend = [
        _confidence_score(str(row.get("confidence") or ""))
        for row in sorted(dated_rows, key=lambda row: _date_key(str(row.get("date") or "")))
    ]
    if message_count >= 4 and actor_count >= 2 and thread_count >= 2:
        primary: RecurrenceLabel = "systematic"
    elif _is_escalating(message_count, confidence_trend, dated_rows):
        primary = "escalating"
    else:
        primary = "repeated"
    return primary, flags


def _is_escalating(message_count: int, confidence_trend: list[int], dated_rows: list[dict[str, Any]]) -> bool:
    escalation_ids = {"escalation", "deadline_pressure", "public_correction"}
    return (
        message_count >= 3
        and bool(confidence_trend)
        and confidence_trend[-1] >= confidence_trend[0]
        and any(str(row.get("behavior_id") or "") in escalation_ids for row in dated_rows)
    )


def _recurrence_flags(message_count, actor_count, thread_count, target_actor_id, linked_count, sender_ids):
    flags: list[RecurrenceLabel] = []
    if target_actor_id and linked_count >= 2 and len(_ordered_unique(sender_ids)) == 1 and message_count >= 2:
        flags.append("targeted")
    if actor_count >= 2 and thread_count >= 2 and message_count >= 3:
        flags.append("possibly_coordinated")
    return flags


def _pattern_summary(
    *,
    cluster_type: Literal["behavior", "taxonomy", "thread"],
    key: str,
    rows: list[dict[str, Any]],
    target_actor_id: str,
) -> PatternSummary:
    """Build one conservative pattern summary from clustered message rows."""
    ordered_rows = _ordered_pattern_rows(rows)
    message_uids = _row_values(ordered_rows, "uid")
    actor_ids = _row_values(ordered_rows, "sender_actor_id")
    thread_group_ids = _row_values(ordered_rows, "thread_group_id")
    primary_recurrence, recurrence_flags = _primary_recurrence(
        message_count=len(message_uids),
        actor_count=len(actor_ids),
        thread_count=len(thread_group_ids),
        target_actor_id=target_actor_id,
        target_linked_count=sum(1 for row in ordered_rows if bool(row.get("target_linked"))),
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
        "first_date": _boundary_date(ordered_rows, 0),
        "last_date": _boundary_date(ordered_rows, -1),
        "primary_recurrence": primary_recurrence,
        "recurrence_flags": recurrence_flags,
    }


def _ordered_pattern_rows(rows):
    return sorted(rows, key=lambda row: (_date_key(str(row.get("date") or "")), str(row.get("uid") or "")))


def _row_values(rows, key):
    return _ordered_unique([str(row.get(key) or "") for row in rows])


def _boundary_date(rows, index):
    return str(rows[index].get("date") or "") if rows else ""


def _communication_classes(candidate: dict[str, Any]) -> list[str]:
    """Return applied communication classes for one candidate."""
    findings = _authored_findings(candidate)
    if not findings:
        return []
    classification = findings.get("communication_classification")
    if isinstance(classification, dict):
        applied_classes = [str(label) for label in classification.get("applied_classes", []) if str(label).strip()]
        if applied_classes:
            return applied_classes
        primary = str(classification.get("primary_class") or "").strip()
        if primary:
            return [primary]
    behavior_ids = _behavior_ids(candidate)
    classes: list[str] = []
    if behavior_ids & {"exclusion", "withholding", "selective_non_response"}:
        classes.append("exclusionary")
    if behavior_ids & {"deadline_pressure", "selective_accountability", "escalation"}:
        classes.append("controlling")
    if behavior_ids & {"public_correction", "undermining", "blame_shifting"}:
        classes.append("dismissive")
    if not classes:
        classes.append("neutral")
    return _ordered_unique(classes)


def _recipient_signature(candidate: dict[str, Any]) -> str:
    """Return a stable visible-recipient signature for comparability checks."""
    summary = _as_dict(candidate.get("recipients_summary"))
    emails = [str(email).strip().lower() for email in summary.get("visible_recipient_emails", []) if str(email).strip()]
    if emails:
        return "|".join(sorted(set(emails)))
    return str(summary.get("signature") or "").strip().lower()


def _candidate_has_target_linkage(candidate: dict[str, Any], *, target_actor_id: str) -> bool:
    """Return whether one candidate carries explicit target-linkage evidence."""
    if not target_actor_id:
        return False
    explicit_target_ids = {
        str(candidate.get("target_actor_id") or "").strip(),
        str(candidate.get("case_target_actor_id") or "").strip(),
    }
    if target_actor_id in explicit_target_ids:
        return True
    reply_pairing = _as_dict(candidate.get("reply_pairing"))
    if bool(reply_pairing.get("target_authored_request")):
        return True
    authored = _authored_findings(candidate)
    behavior_ids = _behavior_ids(candidate)
    if behavior_ids & {"exclusion", "withholding"}:
        return True
    process_signals = {
        str(item.get("signal") or "") for item in authored.get("omissions_or_process_signals", []) if isinstance(item, dict)
    }
    return "target_absent_from_visible_recipients" in process_signals


def _recurring_phrases(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return recurring wording items from per-message review fields."""
    phrase_rows, first_seen_order = _phrase_occurrences(candidates)
    recurring: list[dict[str, Any]] = []
    for phrase, rows in phrase_rows.items():
        message_uids = _ordered_unique([row["uid"] for row in rows if row.get("uid")])
        if len(message_uids) < 2:
            continue
        recurring.append(
            {
                "phrase": phrase,
                "message_count": len(message_uids),
                "message_uids": message_uids,
                "strength": "moderate" if len(message_uids) >= 3 else "weak",
            }
        )
    recurring.sort(
        key=lambda item: (
            -int(item.get("message_count") or 0),
            int(first_seen_order.get(str(item.get("phrase") or ""), 0)),
        )
    )
    return recurring[:10]


def _phrase_occurrences(candidates):
    phrase_rows = defaultdict(list)
    first_seen_order = {}
    for candidate in candidates:
        for item in _authored_findings(candidate).get("relevant_wording", []) or []:
            if not isinstance(item, dict) or not (phrase := str(item.get("text") or "").strip().lower()):
                continue
            first_seen_order.setdefault(phrase, len(first_seen_order))
            phrase_rows[phrase].append({"uid": str(candidate.get("uid") or ""), "date": str(candidate.get("date") or "")})
    return phrase_rows, first_seen_order


def _escalation_points(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return message-level escalation points for the corpus review."""
    items: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: (_date_key(str(item.get("date") or "")), str(item.get("uid") or ""))):
        if item := _escalation_item(candidate):
            items.append(item)
    return items[:10]


def _escalation_item(candidate):
    ids = _behavior_ids(candidate) | _event_behavior_ids(candidate)
    triggers = [
        item for item in ("escalation", "deadline_pressure", "public_correction", "selective_accountability") if item in ids
    ]
    if not triggers:
        return None
    confidence = max(
        _confidence_score(str(candidate.get("detected_language_confidence") or "")), _event_confidence_score(candidate)
    )
    strength = "strong" if len(triggers) >= 2 and confidence >= 2 else "moderate" if confidence >= 2 else "weak"
    event_ids = _event_kind_ids(candidate)
    return {
        "uid": str(candidate.get("uid") or ""),
        "date": str(candidate.get("date") or ""),
        "sender_actor_id": str(candidate.get("sender_actor_id") or ""),
        "triggers": triggers,
        "event_trigger_ids": event_ids,
        "event_trigger_count": len(event_ids),
        "strength": strength,
        "why_it_matters": "The message contains explicit pressure, escalation, or control cues"
        + (" corroborated by extracted event signals." if event_ids else "."),
    }


def _double_standards(candidates: list[dict[str, Any]], *, target_actor_id: str) -> list[dict[str, Any]]:
    """Return bounded double-standard reads from sender-level message contrasts."""
    by_sender: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        sender_actor_id = str(candidate.get("sender_actor_id") or "")
        if sender_actor_id:
            by_sender[sender_actor_id].append(candidate)
    items: list[dict[str, Any]] = []
    for sender_actor_id, sender_candidates in sorted(by_sender.items()):
        target_messages = _target_pressure_messages(sender_candidates, target_actor_id)
        if not target_messages:
            continue
        comparator_messages = [str(candidate.get("uid") or "") for candidate in sender_candidates if not _behavior_ids(candidate)]
        if not comparator_messages:
            continue
        items.append(
            {
                "sender_actor_id": sender_actor_id,
                "target_actor_id": target_actor_id,
                "target_message_uids": _ordered_unique(target_messages),
                "comparator_message_uids": _ordered_unique(comparator_messages),
                "strength": "weak",
                "why_it_matters": "The same sender shows higher-control cues in some messages than in others.",
            }
        )
    return items[:5]


def _target_pressure_messages(candidates, target_actor_id):
    pressure_ids = {"selective_accountability", "public_correction", "deadline_pressure"}
    return [
        str(candidate.get("uid") or "")
        for candidate in candidates
        if _behavior_ids(candidate) & pressure_ids and _candidate_has_target_linkage(candidate, target_actor_id=target_actor_id)
    ]


def _procedural_irregularities(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return omission or process irregularity items from per-message review fields."""
    items: list[dict[str, Any]] = []
    for candidate in candidates:
        findings = _authored_findings(candidate)
        signals = [
            str(item.get("signal") or "")
            for item in findings.get("omissions_or_process_signals", [])
            if isinstance(item, dict) and str(item.get("signal") or "").strip()
        ]
        if not signals:
            continue
        items.append(
            {
                "uid": str(candidate.get("uid") or ""),
                "date": str(candidate.get("date") or ""),
                "irregularity_types": signals,
                "strength": "moderate" if len(signals) >= 2 else "weak",
                "why_it_matters": "The message contains omission-aware or process-irregularity cues.",
            }
        )
    return items[:10]


def _response_timing_shifts(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return bounded response-timing shifts for target-authored requests."""
    requests = [
        candidate
        for candidate in sorted(candidates, key=lambda item: (_date_key(str(item.get("date") or "")), str(item.get("uid") or "")))
        if bool(_as_dict(candidate.get("reply_pairing")).get("target_authored_request"))
    ]
    items: list[dict[str, Any]] = []
    for before, after in pairwise(requests):
        if item := _response_timing_item(before, after):
            items.append(item)
    return items[:5]


def _response_timing_item(before, after):
    basis = _comparability_basis(before, after)
    if not basis:
        return None
    before_pairing, after_pairing = _as_dict(before.get("reply_pairing")), _as_dict(after.get("reply_pairing"))
    before_status, after_status = (
        str(before_pairing.get("response_status") or ""),
        str(after_pairing.get("response_status") or ""),
    )
    before_delay, after_delay = (
        float(before_pairing.get("response_delay_hours") or 0),
        float(after_pairing.get("response_delay_hours") or 0),
    )
    if not (
        (before_status == "direct_reply" and after_status != "direct_reply")
        or after_delay > max(before_delay * 2, before_delay + 24)
    ):
        return None
    return {
        "from_uid": str(before.get("uid") or ""),
        "to_uid": str(after.get("uid") or ""),
        "before_status": before_status,
        "after_status": after_status,
        "shift_label": "worsened_response",
        "comparability_basis": basis,
        "why_it_matters": "Later target-authored requests received weaker or slower response handling.",
    }


def _comparability_basis(before, after):
    before_thread, after_thread = str(before.get("thread_group_id") or ""), str(after.get("thread_group_id") or "")
    if before_thread and before_thread == after_thread:
        return "same_thread_group"
    before_signature, after_signature = _recipient_signature(before), _recipient_signature(after)
    return "same_visible_recipient_signature" if before_signature and before_signature == after_signature else ""


def _cc_behavior_changes(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return sender-level visible-recipient and CC changes."""
    by_sender: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        sender_actor_id = str(candidate.get("sender_actor_id") or "")
        if sender_actor_id:
            by_sender[sender_actor_id].append(candidate)
    items: list[dict[str, Any]] = []
    for sender_actor_id, sender_candidates in sorted(by_sender.items()):
        ordered = sorted(sender_candidates, key=lambda item: (_date_key(str(item.get("date") or "")), str(item.get("uid") or "")))
        for before, after in pairwise(ordered):
            change_types = _recipient_change_types(before, after)
            if change_types:
                items.append(
                    {
                        "sender_actor_id": sender_actor_id,
                        "from_uid": str(before.get("uid") or ""),
                        "to_uid": str(after.get("uid") or ""),
                        "change_types": change_types,
                        "why_it_matters": "Visible recipient routing changed across messages from the same sender.",
                    }
                )
    return items[:10]


def _recipient_change_types(before, after):
    changes = []
    if _recipient_signature(before) != _recipient_signature(after):
        changes.append("visible_recipient_signature_changed")
    before_summary, after_summary = _as_dict(before.get("recipients_summary")), _as_dict(after.get("recipients_summary"))
    if int(after_summary.get("cc_count") or 0) > int(before_summary.get("cc_count") or 0):
        changes.append("cc_count_increase")
    return changes


def _coordination_windows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return short windows with multiple actors using pressure cues."""
    pressure_candidates = [row for candidate in candidates if (row := _pressure_candidate(candidate))]
    items: list[dict[str, Any]] = []
    for anchor in pressure_candidates:
        if item := _coordination_window_item(anchor, pressure_candidates):
            items.append(item)
    return _unique_coordination_windows(items)[:5]


def _pressure_candidate(candidate):
    behavior_ids = _behavior_ids(candidate) | _event_behavior_ids(candidate)
    parsed = _parse_datetime(str(candidate.get("date") or ""))
    if not behavior_ids & {"escalation", "deadline_pressure", "selective_accountability"} or parsed is None:
        return None
    return {
        **candidate,
        "_parsed_date": parsed,
        "_behavior_ids": sorted(behavior_ids),
        "_event_kind_ids": _event_kind_ids(candidate),
    }


def _coordination_window_item(anchor, candidates):
    anchor_dt = anchor["_parsed_date"]
    rows = _window_rows(candidates, anchor_dt)
    actor_ids = sorted(_row_values(rows, "sender_actor_id"))
    if len(actor_ids) < 2:
        return None
    contexts = _shared_context_types(rows)
    if not contexts:
        return None
    return {
        "window_start": str(anchor.get("date") or ""),
        "window_end": str(rows[-1].get("date") or ""),
        "actor_ids": actor_ids,
        "message_uids": _row_values(rows, "uid"),
        "shared_behavior_ids": _nested_row_values(rows, "_behavior_ids"),
        "shared_event_ids": _nested_row_values(rows, "_event_kind_ids"),
        "shared_context_types": contexts,
        "strength": "moderate" if len(actor_ids) >= 3 else "weak",
    }


def _window_rows(candidates, anchor_dt):
    return [row for row in candidates if 0 <= (row["_parsed_date"] - anchor_dt).total_seconds() <= 172800]


def _shared_context_types(rows):
    thread_counts = Counter(str(row.get("thread_group_id") or "") for row in rows if row.get("thread_group_id"))
    signature_counts = Counter(_recipient_signature(row) for row in rows if _recipient_signature(row))
    contexts = []
    if any(key and count >= 2 for key, count in thread_counts.items()):
        contexts.append("shared_thread_group")
    if any(key and count >= 2 for key, count in signature_counts.items()):
        contexts.append("shared_visible_recipient_signature")
    return contexts


def _nested_row_values(rows, key):
    return _ordered_unique([item for row in rows for item in row.get(key, [])])


def _unique_coordination_windows(items):
    unique, seen = [], set()
    for item in items:
        key = (str(item.get("window_start") or ""), "|".join(item.get("actor_ids", [])))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _corpus_behavioral_review(candidates: list[dict[str, Any]], *, target_actor_id: str) -> dict[str, Any]:
    """Return corpus-wide behaviour review data derived from message-level outputs."""
    class_counts: Counter[str] = Counter()
    for candidate in candidates:
        for label in _communication_classes(candidate):
            class_counts[label] += 1
    return {
        "coverage_scope": "retrieved_candidate_slice",
        "scope_note": "Derived from the currently retrieved candidate slice, not from an asserted exhaustive corpus review.",
        "message_count_reviewed": len(candidates),
        "communication_class_counts": dict(sorted(class_counts.items())),
        "recurring_phrases": _recurring_phrases(candidates),
        "escalation_points": _escalation_points(candidates),
        "double_standards": _double_standards(candidates, target_actor_id=target_actor_id),
        "procedural_irregularities": _procedural_irregularities(candidates),
        "response_timing_shifts": _response_timing_shifts(candidates),
        "cc_behavior_changes": _cc_behavior_changes(candidates),
        "coordination_windows": _coordination_windows(candidates),
    }


def build_case_patterns(
    *,
    candidates: list[dict[str, Any]],
    target_actor_id: str = "",
) -> dict[str, Any]:
    """Aggregate BA6 message findings into conservative case-level pattern summaries."""
    behavior_rows, taxonomy_rows, thread_rows, directional_rows, all_rows = _cluster_rows(candidates, target_actor_id)

    behavior_summaries = _cluster_summaries("behavior", behavior_rows, target_actor_id)
    taxonomy_summaries = _cluster_summaries("taxonomy", taxonomy_rows, target_actor_id)
    thread_summaries = _cluster_summaries("thread", thread_rows, target_actor_id)
    directional_summaries = _directional_summaries(directional_rows)
    cluster_index = _cluster_index(all_rows)
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
        "corpus_behavioral_review": _corpus_behavioral_review(candidates, target_actor_id=target_actor_id),
    }


def _cluster_summaries(cluster_type, grouped_rows, target_actor_id):
    return [
        _pattern_summary(cluster_type=cluster_type, key=key, rows=rows, target_actor_id=target_actor_id)
        for key, rows in sorted(grouped_rows.items())
    ]


def _directional_summaries(grouped_rows):
    summaries = []
    for (sender_id, target_id), rows in sorted(grouped_rows.items()):
        message_uids = _row_values(rows, "uid")
        counts = Counter(str(row.get("behavior_id") or "") for row in rows)
        summaries.append(
            {
                "sender_actor_id": sender_id,
                "target_actor_id": target_id,
                "message_count": len(message_uids),
                "behavior_counts": dict(sorted(counts.items())),
                "message_uids": message_uids,
            }
        )
    return summaries


def _cluster_index(rows):
    return [
        {key: str(row.get(key) or "") for key in ("uid", "behavior_id", "sender_actor_id", "thread_group_id", "date")}
        for row in _ordered_pattern_rows(rows)
    ]


def _cluster_rows(candidates, target_actor_id):
    behavior_rows, taxonomy_rows, thread_rows, directional_rows = (
        defaultdict(list),
        defaultdict(list),
        defaultdict(list),
        defaultdict(list),
    )
    all_rows = []
    for candidate in candidates:
        _add_candidate_cluster_rows(
            candidate, target_actor_id, behavior_rows, taxonomy_rows, thread_rows, directional_rows, all_rows
        )
    return behavior_rows, taxonomy_rows, thread_rows, directional_rows, all_rows


def _add_candidate_cluster_rows(
    candidate, target_actor_id, behavior_rows, taxonomy_rows, thread_rows, directional_rows, all_rows
):
    findings = candidate.get("message_findings")
    if not isinstance(findings, dict):
        return
    common = {
        "uid": str(candidate.get("uid") or ""),
        "date": str(candidate.get("date") or ""),
        "sender_actor_id": str(candidate.get("sender_actor_id") or ""),
        "thread_group_id": str(candidate.get("thread_group_id") or ""),
        "target_linked": _candidate_has_target_linkage(candidate, target_actor_id=target_actor_id),
    }
    _add_authored_cluster_rows(
        findings.get("authored_text"),
        common,
        target_actor_id,
        behavior_rows,
        taxonomy_rows,
        thread_rows,
        directional_rows,
        all_rows,
    )
    _add_event_cluster_rows(
        candidate, common, target_actor_id, behavior_rows, taxonomy_rows, thread_rows, directional_rows, all_rows
    )


def _add_authored_cluster_rows(
    authored, common, target_id, behavior_rows, taxonomy_rows, thread_rows, directional_rows, all_rows
):
    if not isinstance(authored, dict):
        return
    for item in authored.get("behavior_candidates", []):
        if isinstance(item, dict):
            row = {**common, "behavior_id": str(item.get("behavior_id") or ""), "confidence": str(item.get("confidence") or "")}
            _store_cluster_row(
                row,
                item.get("taxonomy_ids", []),
                target_id,
                behavior_rows,
                taxonomy_rows,
                thread_rows,
                directional_rows,
                all_rows,
            )


def _add_event_cluster_rows(candidate, common, target_id, behavior_rows, taxonomy_rows, thread_rows, directional_rows, all_rows):
    confidence = "medium" if _event_confidence_score(candidate) >= 2 else "low"
    for behavior_id in sorted(_event_behavior_ids(candidate)):
        _store_cluster_row(
            {**common, "behavior_id": behavior_id, "confidence": confidence},
            [],
            target_id,
            behavior_rows,
            taxonomy_rows,
            thread_rows,
            directional_rows,
            all_rows,
        )


def _store_cluster_row(row, taxonomy_ids, target_actor_id, behavior_rows, taxonomy_rows, thread_rows, directional_rows, all_rows):
    all_rows.append(row)
    behavior_rows[row["behavior_id"]].append(row)
    for taxonomy_id in taxonomy_ids:
        taxonomy_rows[str(taxonomy_id)].append(row)
    if row["thread_group_id"]:
        thread_rows[row["thread_group_id"]].append(row)
    if row["sender_actor_id"] and row["target_linked"]:
        directional_rows[(row["sender_actor_id"], target_actor_id)].append(row)
