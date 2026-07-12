"""Pure section builders for investigation-style reports."""
# pylint: disable=too-many-locals

from __future__ import annotations

from collections import Counter
from typing import Any

from ._utils import _as_dict, _as_list


def _title(label: str) -> str:
    """Convert a label string to a human-readable title format.

    Replaces underscores with spaces and capitalizes the result.
    """
    return str(label or "").replace("_", " ").capitalize()


def _actor_label(event: dict[str, Any]) -> str:
    """Extract a human-readable actor label from an event dictionary.

    Combines sender_name and sender_email if both are present.
    Falls back to whichever is available, or 'unknown sender'.
    """
    sender_name = str(event.get("sender_name") or "").strip()
    sender_email = str(event.get("sender_email") or "").strip()
    if sender_name and sender_email:
        return f"{sender_name} <{sender_email}>"
    return sender_name or sender_email or "unknown sender"


def _recipient_summary_phrase(summary: dict[str, Any]) -> str:
    """Generate a human-readable summary of recipient information.

    Args:
        summary: Dictionary containing recipient summary data with keys like
            'status', 'visible_recipient_count', 'visible_recipient_emails'.

    Returns:
        A string describing the recipient visibility status.
    """
    if str(summary.get("status") or "") != "available":
        return "recipient visibility not available"
    count = int(summary.get("visible_recipient_count") or 0)
    if count <= 0:
        return "no visible recipients"
    emails = [str(email) for email in _as_list(summary.get("visible_recipient_emails")) if email]
    preview = ", ".join(emails[:2])
    if count > 2:
        preview = f"{preview}, +{count - 2} more"
    return f"{count} visible recipient(s): {preview}".strip()


def _section_with_entries(
    *,
    section_id: str,
    title: str,
    entries: list[dict[str, Any]],
    insufficiency_reason: str,
) -> dict[str, Any]:
    """Create a section dictionary with entries or insufficiency reason.

    Args:
        section_id: Unique identifier for the section.
        title: Human-readable title for the section.
        entries: List of entry dictionaries to include.
        insufficiency_reason: Reason to display if entries is empty.

    Returns:
        A section dictionary with status 'supported' if entries exist,
        or 'insufficient_evidence' with the reason if entries is empty.
    """
    if entries:
        return {
            "section_id": section_id,
            "title": title,
            "status": "supported",
            "entries": entries,
            "insufficiency_reason": "",
        }
    return {
        "section_id": section_id,
        "title": title,
        "status": "insufficient_evidence",
        "entries": [],
        "insufficiency_reason": insufficiency_reason,
    }


def _language_section(candidates: list[dict[str, Any]], case_patterns: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the language analysis section from candidate evidence.

    Args:
        candidates: List of candidate dictionaries with language analysis data.
        case_patterns: Optional dictionary containing corpus behavioral review patterns.

    Returns:
        A section dictionary with language signal entries and message behavioral review.
    """
    signal_counts, signal_uids, sampled_messages = _language_data(candidates)
    entries = [
        {
            "entry_id": f"language:{signal_id}",
            "statement": f"{_title(signal_id)} appears in {count} authored message(s).",
            "supporting_finding_ids": [],
            "supporting_citation_ids": [],
            "supporting_uids": signal_uids.get(signal_id, [])[:3],
        }
        for signal_id, count in signal_counts.most_common(3)
    ]
    section = _section_with_entries(
        section_id="language_analysis",
        title="Language Analysis",
        entries=entries,
        insufficiency_reason="No authored language-signal evidence was detected in the current case bundle.",
    )
    section["message_behavioral_review"] = {
        "message_count": len(sampled_messages),
        "sampled_messages": sampled_messages,
    }
    retrieval_slice_review = dict(_as_dict(case_patterns).get("corpus_behavioral_review") or {})
    retrieval_slice_review.setdefault("coverage_scope", "retrieved_candidate_slice")
    retrieval_slice_review.setdefault(
        "scope_note",
        "Derived from the currently retrieved candidate slice, not from an asserted exhaustive corpus review.",
    )
    section["retrieval_slice_behavioral_review"] = retrieval_slice_review
    return section


def _language_data(candidates: list[dict[str, Any]]) -> tuple[Counter[str], dict[str, list[str]], list[dict[str, Any]]]:
    counts: Counter[str] = Counter()
    uids: dict[str, list[str]] = {}
    samples: list[dict[str, Any]] = []
    for candidate in candidates:
        _collect_language_signals(candidate, counts, uids)
        sample = _language_sample(candidate)
        if sample and len(samples) < 4:
            samples.append(sample)
    return counts, uids, samples


def _collect_language_signals(candidate: dict[str, Any], counts: Counter[str], uids: dict[str, list[str]]) -> None:
    uid = str(candidate.get("uid") or "")
    signals = _as_list(_as_dict(_as_dict(candidate.get("language_rhetoric")).get("authored_text")).get("signals"))
    for signal in signals:
        if not isinstance(signal, dict) or not (signal_id := str(signal.get("signal_id") or "")):
            continue
        counts[signal_id] += 1
        if uid and uid not in uids.setdefault(signal_id, []):
            uids[signal_id].append(uid)


def _language_sample(candidate: dict[str, Any]) -> dict[str, Any] | None:
    findings = _as_dict(_as_dict(candidate.get("message_findings")).get("authored_text"))
    if not findings:
        return None
    return {
        "uid": str(candidate.get("uid") or ""),
        "tone_summary": str(findings.get("tone_summary") or ""),
        "communication_classification": dict(findings.get("communication_classification") or {}),
        "relevant_wording": [dict(item) for item in _as_list(findings.get("relevant_wording")) if isinstance(item, dict)],
        "omissions_or_process_signals": [
            dict(item) for item in _as_list(findings.get("omissions_or_process_signals")) if isinstance(item, dict)
        ],
    }


def _timeline_section(
    case_bundle: dict[str, Any],
    timeline: dict[str, Any],
    case_patterns: dict[str, Any],
) -> dict[str, Any]:
    """Build the chronological pattern analysis section from timeline data.

    Args:
        case_bundle: Dictionary containing case bundle data including scope.
        timeline: Dictionary containing timeline events and metadata.
        case_patterns: Dictionary containing behavior patterns for the case.

    Returns:
        A section dictionary with timeline entries and pattern analysis.
    """
    scope = _as_dict(case_bundle.get("scope"))
    events = [event for event in _as_list(timeline.get("events")) if isinstance(event, dict)]
    entries = _timeline_anchor_entries(events, timeline)
    entries.extend(_timeline_sequence_entry(timeline))
    entries.extend(_timeline_trigger_entries(_as_list(scope.get("trigger_events")), events))
    entries.extend(_timeline_pattern_entries(_as_list(case_patterns.get("behavior_patterns"))))
    return _section_with_entries(
        section_id="chronological_pattern_analysis",
        title="Chronological Pattern Analysis",
        entries=entries[:7],
        insufficiency_reason=(
            "The current case bundle does not yet contain enough chronological evidence to describe a pattern over time."
        ),
    )


def _timeline_sequence_entry(timeline: dict[str, Any]) -> list[dict[str, Any]]:
    event_count = int(timeline.get("event_count") or 0)
    if not event_count:
        return []
    date_range = _as_dict(timeline.get("date_range"))
    first_date = date_range.get("first") or "unknown"
    last_date = date_range.get("last") or "unknown"
    return [
        {
            "entry_id": "timeline:sequence_summary",
            "statement": (
                f"The current chronology contains {event_count} dated event(s) from "
                f"{first_date!s} to {last_date!s}, with "
                f"{int(timeline.get('sender_change_count') or 0)} sender change(s), "
                f"{int(timeline.get('thread_change_count') or 0)} thread change(s), and "
                f"{int(timeline.get('recipient_set_change_count') or 0)} visible recipient-set change(s)."
            ),
            "supporting_finding_ids": [],
            "supporting_citation_ids": [],
            "supporting_uids": [
                str(uid)
                for uid in (
                    timeline.get("first_uid"),
                    timeline.get("key_transition_uid"),
                    timeline.get("last_uid"),
                )
                if uid
            ],
        }
    ]


def _timeline_trigger_entries(trigger_events: list[Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries = []
    for index, trigger_event in enumerate(trigger_events[:2], start=1):
        trigger_date = str(trigger_event.get("date") or "")[:10]
        before_count = len([event for event in events if str(event.get("date") or "")[:10] < trigger_date])
        after_count = len([event for event in events if str(event.get("date") or "")[:10] > trigger_date])
        entries.append(
            {
                "entry_id": f"timeline:trigger:{index}",
                "statement": (
                    f"Supplied {_title(str(trigger_event.get('trigger_type') or 'trigger')).lower()} trigger on "
                    f"{trigger_date or 'unknown date'} provides a before/after anchor with "
                    f"{before_count} event(s) before and {after_count} event(s) after."
                ),
                "supporting_finding_ids": [],
                "supporting_citation_ids": [],
                "supporting_uids": [],
            }
        )
    return entries


def _timeline_pattern_entries(summaries: list[Any]) -> list[dict[str, Any]]:
    entries = []
    for summary in summaries[:3]:
        if not isinstance(summary, dict):
            continue
        cluster_id = str(summary.get("cluster_id") or "")
        recurrence = str(summary.get("primary_recurrence") or "")
        key = str(summary.get("key") or "pattern")
        flags = [str(flag) for flag in _as_list(summary.get("recurrence_flags")) if flag]
        flag_suffix = f" Flags: {', '.join(flags)}." if flags else ""
        entries.append(
            {
                "entry_id": f"pattern:{cluster_id}",
                "statement": (
                    f"{_title(key)} currently reads as {recurrence or 'unclassified'} from "
                    f"{str(summary.get('first_date') or '')[:10] or 'unknown'} to "
                    f"{str(summary.get('last_date') or '')[:10] or 'unknown'} across "
                    f"{int(summary.get('message_count') or 0)} message(s) and "
                    f"{len(_as_list(summary.get('thread_group_ids')))} thread group(s).{flag_suffix}"
                ),
                "supporting_finding_ids": [cluster_id] if cluster_id else [],
                "supporting_citation_ids": [],
                "supporting_uids": [str(uid) for uid in _as_list(summary.get("message_uids"))[:3] if uid],
            }
        )
    return entries


def _timeline_anchor_entries(events: list[dict[str, Any]], timeline: dict[str, Any]) -> list[dict[str, Any]]:
    key = str(timeline.get("key_transition_uid") or "")
    anchors = (
        ("timeline:first_event", events[0] if events else {}),
        ("timeline:key_transition", next((event for event in events if str(event.get("uid") or "") == key), {})),
        ("timeline:last_event", events[-1] if events else {}),
    )
    return [_timeline_anchor_entry(entry_id, event) for entry_id, event in anchors if event]


def _timeline_anchor_entry(entry_id: str, event: dict[str, Any]) -> dict[str, Any]:
    uid = str(event.get("uid") or "")
    date = str(event.get("date") or "")[:10] or "unknown date"
    thread = str(event.get("thread_group_id") or event.get("conversation_id") or "unknown")
    recipient_summary = _recipient_summary_phrase(_as_dict(event.get("recipients_summary")))
    statement = f"Chronology anchor on {date} from {_actor_label(event)} falls in thread {thread} with {recipient_summary}."
    return {
        "entry_id": entry_id,
        "statement": statement,
        "supporting_finding_ids": [],
        "supporting_citation_ids": [],
        "supporting_uids": [uid] if uid else [],
    }


def _power_section(
    power_context: dict[str, Any],
    communication_graph: dict[str, Any],
    comparative_treatment: dict[str, Any],
) -> dict[str, Any]:
    """Build the power and context analysis section from evidence data.

    Args:
        power_context: Dictionary containing role facts and power context.
        communication_graph: Dictionary containing graph findings and evidence chains.
        comparative_treatment: Dictionary containing comparator summaries.

    Returns:
        A section dictionary with power analysis entries and comparator matrix.
    """
    entries = _power_role_entries(power_context)
    graph_findings = [finding for finding in _as_list(communication_graph.get("graph_findings")) if isinstance(finding, dict)]
    entries.extend(_power_graph_entries(graph_findings))
    comparator_summaries = [
        summary for summary in _as_list(comparative_treatment.get("comparator_summaries")) if isinstance(summary, dict)
    ]
    available = next((summary for summary in comparator_summaries if summary.get("status") == "comparator_available"), None)
    entries.extend(_power_comparator_entries(available))
    section = _section_with_entries(
        section_id="power_context_analysis",
        title="Power and Context Analysis",
        entries=entries,
        insufficiency_reason=(
            "The current case bundle lacks enough role, hierarchy, or comparator support to assess power dynamics confidently."
        ),
    )
    section["comparator_matrix"] = _comparator_matrix(available)
    return section


def _power_role_entries(context: dict[str, Any]) -> list[dict[str, Any]]:
    facts = _as_list(context.get("supplied_role_facts"))
    return (
        [
            {
                "entry_id": "power:supplied_role_facts",
                "statement": f"Structured org context provides {len(facts)} supplied role fact(s) for this case.",
                "supporting_finding_ids": [],
                "supporting_citation_ids": [],
                "supporting_uids": [],
            }
        ]
        if facts
        else []
    )


def _power_graph_entries(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not findings:
        return []
    first = findings[0]
    return [
        {
            "entry_id": f"power:{first.get('finding_id') or 'graph'}",
            "statement": "Communication-graph evidence highlights "
            + _title(str(first.get("graph_signal_type") or "graph signal")).lower()
            + ".",
            "supporting_finding_ids": [str(first.get("finding_id") or "")],
            "supporting_citation_ids": [],
            "supporting_uids": [
                str(uid) for uid in _as_list(_as_dict(first.get("evidence_chain")).get("message_uids"))[:3] if uid
            ],
        }
    ]


def _power_comparator_entries(available: object) -> list[dict[str, Any]]:
    if not isinstance(available, dict):
        return []
    finding_id = str(available.get("finding_id") or "")
    return [
        {
            "entry_id": f"power:{finding_id or 'comparator'}",
            "statement": "Comparator evidence is available for target-versus-comparator treatment review.",
            "supporting_finding_ids": [finding_id] if finding_id else [],
            "supporting_citation_ids": [],
            "supporting_uids": [
                str(uid) for uid in _as_list(_as_dict(available.get("evidence_chain")).get("target_uids"))[:2] if uid
            ],
        }
    ]


def _comparator_matrix(available: object) -> dict[str, Any]:
    if not isinstance(available, dict):
        return {}
    matrix = _as_dict(available.get("comparator_matrix"))
    return {
        "row_count": int(matrix.get("row_count") or 0),
        "rows": [dict(row) for row in _as_list(matrix.get("rows"))[:4] if isinstance(row, dict)],
    }


def _evidence_table_section(evidence_table: dict[str, Any]) -> dict[str, Any]:
    """Build the evidence table section from evidence rows.

    Args:
        evidence_table: Dictionary containing rows of evidence data.

    Returns:
        A section dictionary with evidence table entries.
    """
    rows = [row for row in _as_list(evidence_table.get("rows")) if isinstance(row, dict)]
    entries = [
        {
            "entry_id": f"evidence_table:{index}",
            "statement": (
                f"Evidence row for {_title(str(row.get('finding_label') or 'finding')).lower()} "
                f"remains exportable with handle {row.get('evidence_handle') or 'unknown'}."
            ),
            "supporting_finding_ids": [str(row.get("finding_id") or "")] if row.get("finding_id") else [],
            "supporting_citation_ids": [],
            "supporting_uids": [str(row.get("message_or_document_id") or "")] if row.get("message_or_document_id") else [],
        }
        for index, row in enumerate(rows[:3], start=1)
    ]
    return _section_with_entries(
        section_id="evidence_table",
        title="Evidence Table",
        entries=entries,
        insufficiency_reason="No exportable evidence rows are available for this case bundle.",
    )
