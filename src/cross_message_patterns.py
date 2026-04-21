"""Cross-message aggregation helpers for behavioural-analysis case patterns."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from itertools import pairwise
from typing import Any, Literal, TypedDict

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
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


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


def _event_rows(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [item for item in candidate.get("event_records", []) if isinstance(item, dict)]
    if not rows:
        return []
    return [row for row in rows if str(row.get("source_scope") or "") not in {"quoted_body", "forwarded_header"}]


def _event_behavior_ids(candidate: dict[str, Any]) -> set[str]:
    derived: set[str] = set()
    for row in _event_rows(candidate):
        event_kind = str(row.get("event_kind") or "")
        behavior_id = _EVENT_BEHAVIOR_MAP.get(event_kind)
        if behavior_id:
            derived.add(behavior_id)
    return derived


def _event_kind_ids(candidate: dict[str, Any]) -> list[str]:
    return _ordered_unique(
        [str(row.get("event_kind") or "") for row in _event_rows(candidate) if str(row.get("event_kind") or "")]
    )


def _event_confidence_score(candidate: dict[str, Any]) -> int:
    return max([_confidence_score(str(row.get("confidence") or "")) for row in _event_rows(candidate)] or [0])


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
    flags: list[RecurrenceLabel] = []
    if message_count == 1:
        return "isolated", flags
    if target_actor_id and target_linked_count >= 2 and len(_ordered_unique(sender_actor_ids)) == 1 and message_count >= 2:
        flags.append("targeted")
    if actor_count >= 2 and thread_count >= 2 and message_count >= 3:
        flags.append("possibly_coordinated")
    confidence_trend = [
        _confidence_score(str(row.get("confidence") or ""))
        for row in sorted(dated_rows, key=lambda row: _date_key(str(row.get("date") or "")))
    ]
    if message_count >= 4 and actor_count >= 2 and thread_count >= 2:
        primary: RecurrenceLabel = "systematic"
    elif (
        message_count >= 3
        and confidence_trend
        and confidence_trend[-1] >= confidence_trend[0]
        and any(
            str(row.get("behavior_id") or "") in {"escalation", "deadline_pressure", "public_correction"} for row in dated_rows
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
        "first_date": str(ordered_rows[0].get("date") or "") if ordered_rows else "",
        "last_date": str(ordered_rows[-1].get("date") or "") if ordered_rows else "",
        "primary_recurrence": primary_recurrence,
        "recurrence_flags": recurrence_flags,
    }


def _communication_classes(candidate: dict[str, Any]) -> list[str]:
    """Return applied communication classes for one candidate."""
    findings = _as_dict(candidate.get("message_findings")).get("authored_text")
    if not isinstance(findings, dict):
        return []
    classification = findings.get("communication_classification")
    if isinstance(classification, dict):
        applied_classes = [str(label) for label in classification.get("applied_classes", []) if str(label).strip()]
        if applied_classes:
            return applied_classes
        primary = str(classification.get("primary_class") or "").strip()
        if primary:
            return [primary]
    behavior_ids = {
        str(item.get("behavior_id") or "") for item in findings.get("behavior_candidates", []) if isinstance(item, dict)
    }
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


def _as_dict(value: Any) -> dict[str, Any]:
    """Return a dict or an empty dict."""
    return value if isinstance(value, dict) else {}


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
    authored = _as_dict(_as_dict(candidate.get("message_findings")).get("authored_text"))
    behavior_ids = {
        str(item.get("behavior_id") or "") for item in authored.get("behavior_candidates", []) if isinstance(item, dict)
    }
    if behavior_ids & {"exclusion", "withholding"}:
        return True
    process_signals = {
        str(item.get("signal") or "") for item in authored.get("omissions_or_process_signals", []) if isinstance(item, dict)
    }
    return "target_absent_from_visible_recipients" in process_signals


def _recurring_phrases(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return recurring wording items from per-message review fields."""
    phrase_rows: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    first_seen_order: dict[str, int] = {}
    for candidate in candidates:
        uid = str(candidate.get("uid") or "")
        findings = _as_dict(_as_dict(candidate.get("message_findings")).get("authored_text"))
        for item in findings.get("relevant_wording", []) or []:
            if not isinstance(item, dict):
                continue
            phrase = str(item.get("text") or "").strip().lower()
            if not phrase:
                continue
            first_seen_order.setdefault(phrase, len(first_seen_order))
            phrase_rows[phrase].append(
                {
                    "uid": uid,
                    "date": str(candidate.get("date") or ""),
                }
            )
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


def _escalation_points(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return message-level escalation points for the corpus review."""
    items: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: (_date_key(str(item.get("date") or "")), str(item.get("uid") or ""))):
        findings = _as_dict(_as_dict(candidate.get("message_findings")).get("authored_text"))
        behavior_ids = {
            str(item.get("behavior_id") or "") for item in findings.get("behavior_candidates", []) if isinstance(item, dict)
        }
        event_behavior_ids = _event_behavior_ids(candidate)
        combined_behavior_ids = behavior_ids | event_behavior_ids
        triggers = [
            behavior_id
            for behavior_id in ("escalation", "deadline_pressure", "public_correction", "selective_accountability")
            if behavior_id in combined_behavior_ids
        ]
        if not triggers:
            continue
        language_confidence = _confidence_score(str(candidate.get("detected_language_confidence") or ""))
        event_confidence = _event_confidence_score(candidate)
        confidence_floor = max(language_confidence, event_confidence)
        strength = "strong" if len(triggers) >= 2 and confidence_floor >= 2 else "moderate" if confidence_floor >= 2 else "weak"
        event_kind_ids = _event_kind_ids(candidate)
        items.append(
            {
                "uid": str(candidate.get("uid") or ""),
                "date": str(candidate.get("date") or ""),
                "sender_actor_id": str(candidate.get("sender_actor_id") or ""),
                "triggers": triggers,
                "event_trigger_ids": event_kind_ids,
                "event_trigger_count": len(event_kind_ids),
                "strength": strength,
                "why_it_matters": (
                    "The message contains explicit pressure, escalation, or control cues"
                    + (" corroborated by extracted event signals." if event_kind_ids else ".")
                ),
            }
        )
    return items[:10]


def _double_standards(candidates: list[dict[str, Any]], *, target_actor_id: str) -> list[dict[str, Any]]:
    """Return bounded double-standard reads from sender-level message contrasts."""
    by_sender: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        sender_actor_id = str(candidate.get("sender_actor_id") or "")
        if sender_actor_id:
            by_sender[sender_actor_id].append(candidate)
    items: list[dict[str, Any]] = []
    for sender_actor_id, sender_candidates in sorted(by_sender.items()):
        target_messages: list[str] = []
        comparator_messages: list[str] = []
        for candidate in sender_candidates:
            findings = _as_dict(_as_dict(candidate.get("message_findings")).get("authored_text"))
            behavior_ids = {
                str(item.get("behavior_id") or "") for item in findings.get("behavior_candidates", []) if isinstance(item, dict)
            }
            if not behavior_ids & {"selective_accountability", "public_correction", "deadline_pressure"}:
                continue
            if not _candidate_has_target_linkage(candidate, target_actor_id=target_actor_id):
                continue
            target_messages.append(str(candidate.get("uid") or ""))
        if not target_messages:
            continue
        for candidate in sender_candidates:
            findings = _as_dict(_as_dict(candidate.get("message_findings")).get("authored_text"))
            behavior_ids = {
                str(item.get("behavior_id") or "") for item in findings.get("behavior_candidates", []) if isinstance(item, dict)
            }
            if behavior_ids:
                continue
            comparator_messages.append(str(candidate.get("uid") or ""))
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


def _procedural_irregularities(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return omission or process irregularity items from per-message review fields."""
    items: list[dict[str, Any]] = []
    for candidate in candidates:
        findings = _as_dict(_as_dict(candidate.get("message_findings")).get("authored_text"))
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
        before_pairing = _as_dict(before.get("reply_pairing"))
        after_pairing = _as_dict(after.get("reply_pairing"))
        before_thread = str(before.get("thread_group_id") or "")
        after_thread = str(after.get("thread_group_id") or "")
        before_signature = _recipient_signature(before)
        after_signature = _recipient_signature(after)
        comparable = False
        comparability_basis = ""
        if before_thread and before_thread == after_thread:
            comparable = True
            comparability_basis = "same_thread_group"
        elif before_signature and before_signature == after_signature:
            comparable = True
            comparability_basis = "same_visible_recipient_signature"
        if not comparable:
            continue
        before_status = str(before_pairing.get("response_status") or "")
        after_status = str(after_pairing.get("response_status") or "")
        before_delay = float(before_pairing.get("response_delay_hours") or 0)
        after_delay = float(after_pairing.get("response_delay_hours") or 0)
        worsened = (before_status == "direct_reply" and after_status != "direct_reply") or (
            after_delay > max(before_delay * 2, before_delay + 24)
        )
        if not worsened:
            continue
        items.append(
            {
                "from_uid": str(before.get("uid") or ""),
                "to_uid": str(after.get("uid") or ""),
                "before_status": before_status,
                "after_status": after_status,
                "shift_label": "worsened_response",
                "comparability_basis": comparability_basis,
                "why_it_matters": "Later target-authored requests received weaker or slower response handling.",
            }
        )
    return items[:5]


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
            before_summary = _as_dict(before.get("recipients_summary"))
            after_summary = _as_dict(after.get("recipients_summary"))
            change_types: list[str] = []
            if _recipient_signature(before) != _recipient_signature(after):
                change_types.append("visible_recipient_signature_changed")
            if int(after_summary.get("cc_count") or 0) > int(before_summary.get("cc_count") or 0):
                change_types.append("cc_count_increase")
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


def _coordination_windows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return short windows with multiple actors using pressure cues."""
    pressure_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        findings = _as_dict(_as_dict(candidate.get("message_findings")).get("authored_text"))
        behavior_ids = {
            str(item.get("behavior_id") or "") for item in findings.get("behavior_candidates", []) if isinstance(item, dict)
        }
        behavior_ids = behavior_ids | _event_behavior_ids(candidate)
        if not behavior_ids & {"escalation", "deadline_pressure", "selective_accountability"}:
            continue
        parsed = _parse_datetime(str(candidate.get("date") or ""))
        if parsed is None:
            continue
        pressure_candidates.append(
            {
                **candidate,
                "_parsed_date": parsed,
                "_behavior_ids": sorted(behavior_ids),
                "_event_kind_ids": _event_kind_ids(candidate),
            }
        )
    items: list[dict[str, Any]] = []
    for anchor in pressure_candidates:
        anchor_dt = _as_dict(anchor).get("_parsed_date")
        if not isinstance(anchor_dt, datetime):
            continue
        window_rows = []
        for row in pressure_candidates:
            row_dt = _as_dict(row).get("_parsed_date")
            if not isinstance(row_dt, datetime):
                continue
            if 0 <= (row_dt - anchor_dt).total_seconds() <= 172800:
                window_rows.append(row)
        actor_ids = sorted(
            _ordered_unique([str(row.get("sender_actor_id") or "") for row in window_rows if row.get("sender_actor_id")])
        )
        if len(actor_ids) < 2:
            continue
        shared_thread_ids = {
            thread_id
            for thread_id, count in Counter(
                str(row.get("thread_group_id") or "") for row in window_rows if row.get("thread_group_id")
            ).items()
            if thread_id and count >= 2
        }
        shared_recipient_signatures = {
            signature
            for signature, count in Counter(_recipient_signature(row) for row in window_rows if _recipient_signature(row)).items()
            if signature and count >= 2
        }
        shared_context_types: list[str] = []
        if shared_thread_ids:
            shared_context_types.append("shared_thread_group")
        if shared_recipient_signatures:
            shared_context_types.append("shared_visible_recipient_signature")
        if not shared_context_types:
            continue
        items.append(
            {
                "window_start": str(anchor.get("date") or ""),
                "window_end": str(window_rows[-1].get("date") or ""),
                "actor_ids": actor_ids,
                "message_uids": _ordered_unique([str(row.get("uid") or "") for row in window_rows if row.get("uid")]),
                "shared_behavior_ids": _ordered_unique(
                    [behavior_id for row in window_rows for behavior_id in row.get("_behavior_ids", [])]
                ),
                "shared_event_ids": _ordered_unique(
                    [event_id for row in window_rows for event_id in row.get("_event_kind_ids", [])]
                ),
                "shared_context_types": shared_context_types,
                "strength": "moderate" if len(actor_ids) >= 3 else "weak",
            }
        )
    unique_items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (str(item.get("window_start") or ""), "|".join(item.get("actor_ids", [])))
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(item)
    return unique_items[:5]


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
                    "target_linked": _candidate_has_target_linkage(candidate, target_actor_id=target_actor_id),
                }
                behavior_id = str(row.get("behavior_id") or "")
                all_rows.append(row)
                behavior_rows[behavior_id].append(row)
                for taxonomy_id in behavior_candidate.get("taxonomy_ids", []):
                    taxonomy_rows[str(taxonomy_id)].append(row)
                if thread_group_id:
                    thread_rows[thread_group_id].append(row)
                if sender_actor_id and bool(row.get("target_linked")):
                    directional_rows[(sender_actor_id, target_actor_id)].append(row)

        for behavior_id in sorted(_event_behavior_ids(candidate)):
            row = {
                "uid": uid,
                "date": date,
                "sender_actor_id": sender_actor_id,
                "thread_group_id": thread_group_id,
                "behavior_id": behavior_id,
                "confidence": "medium" if _event_confidence_score(candidate) >= 2 else "low",
                "target_linked": _candidate_has_target_linkage(candidate, target_actor_id=target_actor_id),
            }
            all_rows.append(row)
            behavior_rows[behavior_id].append(row)
            if thread_group_id:
                thread_rows[thread_group_id].append(row)
            if sender_actor_id and bool(row.get("target_linked")):
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
        "corpus_behavioral_review": _corpus_behavioral_review(candidates, target_actor_id=target_actor_id),
    }
