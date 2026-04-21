"""Pure section builders for investigation-style reports."""

from __future__ import annotations

from collections import Counter
from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _title(label: str) -> str:
    return str(label or "").replace("_", " ").capitalize()


def _actor_label(event: dict[str, Any]) -> str:
    sender_name = str(event.get("sender_name") or "").strip()
    sender_email = str(event.get("sender_email") or "").strip()
    if sender_name and sender_email:
        return f"{sender_name} <{sender_email}>"
    return sender_name or sender_email or "unknown sender"


def _recipient_summary_phrase(summary: dict[str, Any]) -> str:
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
    signal_counts: Counter[str] = Counter()
    signal_uids: dict[str, list[str]] = {}
    sampled_messages: list[dict[str, Any]] = []
    for candidate in candidates:
        uid = str(candidate.get("uid") or "")
        rhetoric = _as_dict(candidate.get("language_rhetoric"))
        authored_text = _as_dict(rhetoric.get("authored_text"))
        for signal in _as_list(authored_text.get("signals")):
            if not isinstance(signal, dict):
                continue
            signal_id = str(signal.get("signal_id") or "")
            if not signal_id:
                continue
            signal_counts[signal_id] += 1
            signal_uids.setdefault(signal_id, [])
            if uid and uid not in signal_uids[signal_id]:
                signal_uids[signal_id].append(uid)
        message_findings = _as_dict(_as_dict(candidate.get("message_findings")).get("authored_text"))
        if message_findings and len(sampled_messages) < 4:
            sampled_messages.append(
                {
                    "uid": uid,
                    "tone_summary": str(message_findings.get("tone_summary") or ""),
                    "communication_classification": dict(message_findings.get("communication_classification") or {}),
                    "relevant_wording": [
                        dict(item) for item in _as_list(message_findings.get("relevant_wording")) if isinstance(item, dict)
                    ],
                    "omissions_or_process_signals": [
                        dict(item)
                        for item in _as_list(message_findings.get("omissions_or_process_signals"))
                        if isinstance(item, dict)
                    ],
                }
            )
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


def _timeline_section(
    case_bundle: dict[str, Any],
    timeline: dict[str, Any],
    case_patterns: dict[str, Any],
) -> dict[str, Any]:
    scope = _as_dict(case_bundle.get("scope"))
    events = [event for event in _as_list(timeline.get("events")) if isinstance(event, dict)]
    entries: list[dict[str, Any]] = []
    first_event = events[0] if events else {}
    last_event = events[-1] if events else {}
    key_transition_uid = str(timeline.get("key_transition_uid") or "")
    key_transition_event = next(
        (event for event in events if str(event.get("uid") or "") == key_transition_uid),
        {},
    )
    for entry_id, event in (
        ("timeline:first_event", first_event),
        ("timeline:key_transition", key_transition_event),
        ("timeline:last_event", last_event),
    ):
        if not event:
            continue
        uid = str(event.get("uid") or "")
        date = str(event.get("date") or "")[:10] or "unknown date"
        thread_group_id = str(event.get("thread_group_id") or event.get("conversation_id") or "")
        entries.append(
            {
                "entry_id": entry_id,
                "statement": (
                    f"Chronology anchor on {date} from {_actor_label(event)} falls in "
                    f"thread {thread_group_id or 'unknown'} with "
                    f"{_recipient_summary_phrase(_as_dict(event.get('recipients_summary')))}."
                ),
                "supporting_finding_ids": [],
                "supporting_citation_ids": [],
                "supporting_uids": [uid] if uid else [],
            }
        )
    event_count = int(timeline.get("event_count") or 0)
    if event_count > 0:
        date_range = _as_dict(timeline.get("date_range"))
        first_date = date_range.get("first") or "unknown"
        last_date = date_range.get("last") or "unknown"
        entries.append(
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
                    for uid in [
                        timeline.get("first_uid"),
                        timeline.get("key_transition_uid"),
                        timeline.get("last_uid"),
                    ]
                    if uid
                ],
            }
        )
    trigger_events = [event for event in _as_list(scope.get("trigger_events")) if isinstance(event, dict)]
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
    for summary in _as_list(case_patterns.get("behavior_patterns"))[:3]:
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
    return _section_with_entries(
        section_id="chronological_pattern_analysis",
        title="Chronological Pattern Analysis",
        entries=entries[:7],
        insufficiency_reason=(
            "The current case bundle does not yet contain enough chronological evidence to describe a pattern over time."
        ),
    )


def _power_section(
    power_context: dict[str, Any],
    communication_graph: dict[str, Any],
    comparative_treatment: dict[str, Any],
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    supplied_role_facts = _as_list(power_context.get("supplied_role_facts"))
    if supplied_role_facts:
        entries.append(
            {
                "entry_id": "power:supplied_role_facts",
                "statement": f"Structured org context provides {len(supplied_role_facts)} supplied role fact(s) for this case.",
                "supporting_finding_ids": [],
                "supporting_citation_ids": [],
                "supporting_uids": [],
            }
        )
    graph_findings = [finding for finding in _as_list(communication_graph.get("graph_findings")) if isinstance(finding, dict)]
    if graph_findings:
        first = graph_findings[0]
        entries.append(
            {
                "entry_id": f"power:{first.get('finding_id') or 'graph'}",
                "statement": (
                    "Communication-graph evidence highlights "
                    f"{_title(str(first.get('graph_signal_type') or 'graph signal')).lower()}."
                ),
                "supporting_finding_ids": [str(first.get("finding_id") or "")],
                "supporting_citation_ids": [],
                "supporting_uids": [
                    str(uid) for uid in _as_list(_as_dict(first.get("evidence_chain")).get("message_uids"))[:3] if uid
                ],
            }
        )
    comparator_summaries = [
        summary for summary in _as_list(comparative_treatment.get("comparator_summaries")) if isinstance(summary, dict)
    ]
    available = next((summary for summary in comparator_summaries if summary.get("status") == "comparator_available"), None)
    if isinstance(available, dict):
        finding_id = str(available.get("finding_id") or "")
        entries.append(
            {
                "entry_id": f"power:{finding_id or 'comparator'}",
                "statement": "Comparator evidence is available for target-versus-comparator treatment review.",
                "supporting_finding_ids": [finding_id] if finding_id else [],
                "supporting_citation_ids": [],
                "supporting_uids": [
                    str(uid) for uid in _as_list(_as_dict(available.get("evidence_chain")).get("target_uids"))[:2] if uid
                ],
            }
        )
    section = _section_with_entries(
        section_id="power_context_analysis",
        title="Power and Context Analysis",
        entries=entries,
        insufficiency_reason=(
            "The current case bundle lacks enough role, hierarchy, or comparator support to assess power dynamics confidently."
        ),
    )
    comparator_matrix = {}
    if isinstance(available, dict):
        matrix = _as_dict(available.get("comparator_matrix"))
        comparator_matrix = {
            "row_count": int(matrix.get("row_count") or 0),
            "rows": [dict(row) for row in _as_list(matrix.get("rows"))[:4] if isinstance(row, dict)],
        }
    section["comparator_matrix"] = comparator_matrix
    return section


def _evidence_table_section(evidence_table: dict[str, Any]) -> dict[str, Any]:
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
