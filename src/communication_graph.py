"""Communication-graph and exclusion analytics for behavioural-analysis cases."""
# pylint: disable=too-many-branches,too-many-locals,too-many-statements

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

COMMUNICATION_GRAPH_VERSION = "1"
_EMAIL_RE = re.compile(r"(?i)(?:mailto:)?([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})")
_DECISION_OR_UPDATE_RE = re.compile(
    r"(?i)\b("
    r"decid(?:e|ed|ing|es)|decision|decided|approved|finali[sz]ed|agreed|update|updated|next step|"
    r"inform(?:ed|ing)? later|proceed(?:ing)?|move forward|resolved|"
    r"entschied(?:en|ung)?|beschlossen|abgestimmt|weiter(?:gehen|e)|"
    r"informiert(?:en)?|mitgeteilt|vorgehen|entscheidung|beschluss|freig(?:abe|egeben)"
    r")\b"
)
_SUBJECT_PREFIX_RE = re.compile(r"(?i)^\s*(?:re|fw|fwd|aw|wg)\s*:\s*")


def _recipient_records(full_email: dict[str, Any] | None) -> list[dict[str, str]]:
    """Return normalized visible-recipient records from one email row."""
    records: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for channel in ("to", "cc", "bcc"):
        for value in (full_email or {}).get(channel) or []:
            match = _EMAIL_RE.search(str(value or ""))
            if not match:
                continue
            email = match.group(1).lower()
            key = (email, channel)
            if key in seen:
                continue
            seen.add(key)
            records.append({"email": email, "channel": channel})
    return records


def _behavior_ids(candidate: dict[str, Any]) -> set[str]:
    """Return authored behavior ids for one candidate."""
    findings = (candidate.get("message_findings") or {}).get("authored_text") or {}
    return {
        str(behavior.get("behavior_id") or "")
        for behavior in findings.get("behavior_candidates", [])
        if isinstance(behavior, dict) and behavior.get("behavior_id")
    }


def _text_mentions_target(candidate: dict[str, Any], *, target_email: str, target_name: str) -> bool:
    """Return whether the current evidence likely refers to the target."""
    haystacks = [
        str(candidate.get("snippet") or ""),
        str((candidate.get("language_rhetoric") or {}).get("authored_text") or {}),
    ]
    normalized_name = target_name.strip().lower()
    normalized_email = target_email.strip().lower()
    for haystack in haystacks:
        lowered = haystack.lower()
        if normalized_email and normalized_email in lowered:
            return True
        if normalized_name and normalized_name in lowered:
            return True
    return False


def _subject_family(candidate: dict[str, Any]) -> str:
    """Return a conservative normalized topic key from the visible subject."""
    subject = str(candidate.get("subject") or "").strip()
    while subject:
        updated = _SUBJECT_PREFIX_RE.sub("", subject).strip()
        if updated == subject:
            break
        subject = updated
    subject = re.sub(r"\s+", " ", subject.lower()).strip()
    return subject


def _decision_or_update_signal(candidate: dict[str, Any], *, behavior_ids: set[str]) -> bool:
    """Return whether the message reads like a target-relevant update or decision flow."""
    if behavior_ids & {"withholding", "exclusion"}:
        return True
    authored_text = str(candidate.get("snippet") or "")
    return bool(_DECISION_OR_UPDATE_RE.search(authored_text))


def build_communication_graph(
    *,
    case_bundle: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    full_map: dict[str, Any],
) -> dict[str, Any] | None:
    """Return conservative communication-graph analysis for one case-scoped evidence set."""
    scope = (case_bundle or {}).get("scope") if isinstance(case_bundle, dict) else None
    if not isinstance(scope, dict):
        return None
    target_person = scope.get("target_person")
    if not isinstance(target_person, dict):
        return None
    target_email = str(target_person.get("email") or "").lower()
    target_actor_id = str(target_person.get("actor_id") or "")
    target_name = str(target_person.get("name") or "")

    nodes, edges, sender_stats = _collect_graph_data(candidates, full_map, target_email, target_name)
    findings = _graph_findings(sender_stats)

    node_list = sorted(nodes.values(), key=lambda node: node["node_id"])
    edge_list = sorted(
        [
            {
                "from": edge["from"],
                "to": edge["to"],
                "message_count": int(edge["message_count"]),
                "channels": dict(sorted(edge["channels"].items())),
                "message_uids": list(edge["message_uids"]),
            }
            for edge in edges.values()
        ],
        key=lambda edge: (edge["from"], edge["to"]),
    )
    summary = {
        "node_count": len(node_list),
        "edge_count": len(edge_list),
        "sender_count": len(sender_stats),
        "target_actor_id": target_actor_id,
        "target_email": target_email,
        "graph_finding_count": len(findings),
        "finding_counts": dict(sorted(Counter(finding["graph_signal_type"] for finding in findings).items())),
    }
    return {
        "version": COMMUNICATION_GRAPH_VERSION,
        "summary": summary,
        "nodes": node_list,
        "edges": edge_list,
        "graph_findings": findings,
    }


def _collect_graph_data(candidates, full_map, target_email, target_name):
    nodes: dict[str, dict[str, str]] = {}
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    sender_stats: defaultdict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "included_uids": [],
            "excluded_uids": [],
            "target_relevant_included_uids": [],
            "target_relevant_excluded_uids": [],
            "decision_included_uids": [],
            "decision_excluded_uids": [],
            "escalated_uids": [],
            "escalated_included_uids": [],
            "escalated_excluded_uids": [],
            "threads_included": set(),
            "threads_excluded": set(),
            "excluded_subject_families": set(),
            "included_subject_families": set(),
            "decision_subject_families": set(),
            "thread_visibility": defaultdict(
                lambda: {
                    "included_uids": [],
                    "excluded_uids": [],
                    "target_relevant_excluded_uids": [],
                }
            ),
        }
    )
    for candidate in candidates:
        _record_graph_candidate(candidate, full_map, target_email, target_name, nodes, edges, sender_stats)

    return nodes, edges, sender_stats


def _record_graph_candidate(candidate, full_map, target_email, target_name, nodes, edges, sender_stats):
    uid = str(candidate.get("uid") or "")
    sender_actor_id = str(candidate.get("sender_actor_id") or "")
    sender_email = str(candidate.get("sender_email") or "").lower()
    sender_node_id = sender_actor_id or sender_email
    if sender_node_id:
        nodes[sender_node_id] = {
            "node_id": sender_node_id,
            "kind": "actor" if sender_actor_id else "email",
            "email": sender_email,
        }
    recipients = _recipient_records(full_map.get(uid))
    _record_edges(uid, sender_node_id or sender_email, recipients, nodes, edges)
    if sender_node_id:
        _record_sender_stats(candidate, uid, sender_node_id, recipients, target_email, target_name, sender_stats)


def _record_edges(uid, sender_node_id, recipient_records, nodes, edges):
    for record in recipient_records:
        recipient_id = record["email"]
        nodes[recipient_id] = {"node_id": recipient_id, "kind": "email", "email": recipient_id}
        key = (sender_node_id, recipient_id)
        edge = edges.setdefault(
            key, {"from": sender_node_id, "to": recipient_id, "message_count": 0, "channels": Counter(), "message_uids": []}
        )
        edge["message_count"] += 1
        edge["channels"][record["channel"]] += 1
        if uid and uid not in edge["message_uids"]:
            edge["message_uids"].append(uid)


def _record_sender_stats(candidate, uid, sender_id, recipient_records, target_email, target_name, sender_stats):
    recipients = {record["email"] for record in recipient_records}
    thread_id = str(candidate.get("thread_group_id") or "")
    subject = _subject_family(candidate)
    behavior_ids = _behavior_ids(candidate)
    included = bool(target_email and target_email in recipients)
    target_relevant = bool(
        _text_mentions_target(candidate, target_email=target_email, target_name=target_name)
        or behavior_ids & {"exclusion", "withholding", "selective_non_response"}
    )
    decision = _decision_or_update_signal(candidate, behavior_ids=behavior_ids)
    stats = sender_stats[sender_id]
    visibility = stats["thread_visibility"][thread_id or f"uid:{uid}"]
    if included:
        _record_included(stats, visibility, uid, subject, thread_id, target_relevant, decision)
    elif target_email and target_relevant:
        _record_excluded(stats, visibility, uid, subject, thread_id, decision)
    _record_escalation_stats(stats, uid, recipients, behavior_ids, included, target_email, target_relevant)


def _record_escalation_stats(stats, uid, recipients, behavior_ids, included, target_email, target_relevant):
    if len(recipients) < 2 or not behavior_ids & {"escalation", "public_correction"}:
        return
    stats["escalated_uids"].append(uid)
    if included:
        stats["escalated_included_uids"].append(uid)
    elif target_email and target_relevant:
        stats["escalated_excluded_uids"].append(uid)


def _record_included(stats, visibility, uid, subject, thread_id, relevant, decision):
    stats["included_uids"].append(uid)
    visibility["included_uids"].append(uid)
    if subject:
        stats["included_subject_families"].add(subject)
    if thread_id:
        stats["threads_included"].add(thread_id)
    if relevant:
        stats["target_relevant_included_uids"].append(uid)
    if relevant and decision:
        stats["decision_included_uids"].append(uid)


def _record_excluded(stats, visibility, uid, subject, thread_id, decision):
    stats["excluded_uids"].append(uid)
    stats["target_relevant_excluded_uids"].append(uid)
    visibility["excluded_uids"].append(uid)
    visibility["target_relevant_excluded_uids"].append(uid)
    if subject:
        stats["excluded_subject_families"].add(subject)
    if thread_id:
        stats["threads_excluded"].add(thread_id)
    if decision:
        stats["decision_excluded_uids"].append(uid)
        if subject:
            stats["decision_subject_families"].add(subject)


def _graph_findings(sender_stats):
    findings = []
    builders = (
        _repeated_exclusion_finding,
        _visibility_asymmetry_finding,
        _decision_visibility_finding,
        _selective_escalation_finding,
        _escalation_visibility_finding,
        _forked_side_channel_finding,
        _thread_fork_finding,
    )
    for sender_id, stats in sender_stats.items():
        findings.extend(finding for builder in builders if (finding := builder(sender_id, stats)))
    return findings


def _graph_finding(sender_id, signal_type, confidence, basis, summary, evidence_chain, counter_indicator):
    return {
        "finding_id": f"{signal_type}:{sender_id}",
        "graph_signal_type": signal_type,
        "confidence": confidence,
        "evidence_basis": basis,
        "summary": summary,
        "evidence_chain": {"sender_node_id": sender_id, **evidence_chain},
        "counter_indicators": [counter_indicator],
    }


def _repeated_exclusion_finding(sender_id, stats):
    excluded = list(stats["target_relevant_excluded_uids"])
    if len(excluded) < 2:
        return None
    return _graph_finding(
        sender_id,
        "repeated_exclusion",
        "medium",
        "graph_plus_behavior",
        "Same sender repeatedly sends target-relevant messages while the target remains absent from visible recipients.",
        {
            "message_uids": excluded,
            "thread_group_ids": sorted(stats["threads_excluded"]),
            "subject_families": sorted(stats["excluded_subject_families"]),
        },
        "Recipient omission may still have a neutral operational explanation without broader case context.",
    )


def _visibility_asymmetry_finding(sender_id, stats):
    excluded = list(stats["target_relevant_excluded_uids"])
    if not stats["included_uids"] or not excluded:
        return None
    return _graph_finding(
        sender_id,
        "visibility_asymmetry",
        "medium",
        "graph_only",
        "Same sender shows mixed visibility patterns, sometimes including the target and sometimes excluding them.",
        {
            "included_uids": list(stats["included_uids"]),
            "excluded_uids": excluded,
            "subject_families": sorted(stats["included_subject_families"] | stats["excluded_subject_families"]),
        },
        "Different recipient sets may reflect different process stages rather than hostile exclusion.",
    )


def _decision_visibility_finding(sender_id, stats):
    if not stats["decision_excluded_uids"] or not stats["decision_included_uids"]:
        return None
    return _graph_finding(
        sender_id,
        "decision_visibility_asymmetry",
        "medium",
        "graph_plus_behavior",
        "The same sender shows decision or update handling both with and without the target visible on the recipient list.",
        {
            "included_uids": list(stats["decision_included_uids"]),
            "excluded_uids": list(stats["decision_excluded_uids"]),
            "subject_families": sorted(stats["decision_subject_families"]),
        },
        "Decision-flow visibility can change for neutral workflow or need-to-know reasons.",
    )


def _selective_escalation_finding(sender_id, stats):
    if not stats["escalated_uids"] or not stats["included_uids"]:
        return None
    return _graph_finding(
        sender_id,
        "selective_escalation",
        "low",
        "graph_plus_behavior",
        "Same sender uses multi-recipient escalation or correction patterns in target-related messages.",
        {"message_uids": list(stats["escalated_uids"])},
        "Broader recipient visibility may be required for operational escalation or recordkeeping.",
    )


def _escalation_visibility_finding(sender_id, stats):
    if not stats["escalated_included_uids"] or not stats["escalated_excluded_uids"]:
        return None
    return _graph_finding(
        sender_id,
        "escalation_visibility_asymmetry",
        "medium",
        "graph_plus_behavior",
        (
            "The same sender shows escalation or public-correction messages both with and without the target visible, "
            "creating a visibility asymmetry around escalation."
        ),
        {"included_uids": list(stats["escalated_included_uids"]), "excluded_uids": list(stats["escalated_excluded_uids"])},
        "Escalation routing can legitimately vary with audience, responsibility, or recordkeeping needs.",
    )


def _forked_side_channel_finding(sender_id, stats):
    shared_threads = sorted(stats["threads_included"] & stats["threads_excluded"])
    if not shared_threads:
        return None
    return _graph_finding(
        sender_id,
        "forked_side_channel",
        "low",
        "graph_only",
        "Same sender shows both included and excluded target communication within the same thread group.",
        {"thread_group_ids": shared_threads},
        "Separate recipient lists within one thread can still be operationally justified.",
    )


def _thread_fork_finding(sender_id, stats):
    fork_threads, fork_uids = _fork_evidence(stats["thread_visibility"])
    if not fork_threads:
        return None
    return _graph_finding(
        sender_id,
        "thread_fork_exclusion",
        "medium",
        "graph_plus_behavior",
        (
            "Within the same thread group, the sender forks target-relevant discussion into branches where the target "
            "is no longer visible."
        ),
        {"thread_group_ids": sorted(fork_threads), "message_uids": fork_uids},
        "Thread-level recipient changes can still arise from legitimate workflow splitting.",
    )


def _fork_evidence(thread_visibility):
    threads, uids = [], []
    for thread_key, visibility in thread_visibility.items():
        if not visibility["included_uids"] or not visibility["target_relevant_excluded_uids"]:
            continue
        if thread_key and not thread_key.startswith("uid:"):
            threads.append(thread_key)
        for uid in [*visibility["included_uids"], *visibility["target_relevant_excluded_uids"]]:
            if uid and uid not in uids:
                uids.append(uid)
    return threads, uids
