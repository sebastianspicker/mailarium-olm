"""Communication-graph and exclusion analytics for behavioural-analysis cases."""

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
    findings: list[dict[str, Any]] = []

    for candidate in candidates:
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
        recipient_records = _recipient_records(full_map.get(uid))
        for record in recipient_records:
            recipient_node_id = record["email"]
            nodes[recipient_node_id] = {
                "node_id": recipient_node_id,
                "kind": "email",
                "email": record["email"],
            }
            edge_key = (sender_node_id or sender_email, recipient_node_id)
            edge = edges.get(edge_key)
            if edge is None:
                edge = {
                    "from": edge_key[0],
                    "to": recipient_node_id,
                    "message_count": 0,
                    "channels": Counter(),
                    "message_uids": [],
                }
                edges[edge_key] = edge
            edge["message_count"] += 1
            edge["channels"][record["channel"]] += 1
            if uid and uid not in edge["message_uids"]:
                edge["message_uids"].append(uid)

        if not sender_node_id:
            continue
        recipients = {record["email"] for record in recipient_records}
        thread_group_id = str(candidate.get("thread_group_id") or "")
        subject_family = _subject_family(candidate)
        behavior_ids = _behavior_ids(candidate)
        target_included = bool(target_email and target_email in recipients)
        target_referenced = _text_mentions_target(candidate, target_email=target_email, target_name=target_name)
        target_relevant = bool(target_referenced or behavior_ids & {"exclusion", "withholding", "selective_non_response"})
        decision_or_update = _decision_or_update_signal(candidate, behavior_ids=behavior_ids)
        thread_visibility = sender_stats[sender_node_id]["thread_visibility"][thread_group_id or f"uid:{uid}"]
        if target_included:
            sender_stats[sender_node_id]["included_uids"].append(uid)
            if subject_family:
                sender_stats[sender_node_id]["included_subject_families"].add(subject_family)
            thread_visibility["included_uids"].append(uid)
            if thread_group_id:
                sender_stats[sender_node_id]["threads_included"].add(thread_group_id)
            if target_relevant:
                sender_stats[sender_node_id]["target_relevant_included_uids"].append(uid)
            if target_relevant and decision_or_update:
                sender_stats[sender_node_id]["decision_included_uids"].append(uid)
        elif target_email and target_relevant:
            sender_stats[sender_node_id]["excluded_uids"].append(uid)
            sender_stats[sender_node_id]["target_relevant_excluded_uids"].append(uid)
            if subject_family:
                sender_stats[sender_node_id]["excluded_subject_families"].add(subject_family)
            thread_visibility["excluded_uids"].append(uid)
            thread_visibility["target_relevant_excluded_uids"].append(uid)
            if thread_group_id:
                sender_stats[sender_node_id]["threads_excluded"].add(thread_group_id)
            if decision_or_update:
                sender_stats[sender_node_id]["decision_excluded_uids"].append(uid)
                if subject_family:
                    sender_stats[sender_node_id]["decision_subject_families"].add(subject_family)
        if len(recipients) >= 2 and behavior_ids & {"escalation", "public_correction"}:
            sender_stats[sender_node_id]["escalated_uids"].append(uid)
            if target_included:
                sender_stats[sender_node_id]["escalated_included_uids"].append(uid)
            elif target_email and target_relevant:
                sender_stats[sender_node_id]["escalated_excluded_uids"].append(uid)

    for sender_node_id, stats in sender_stats.items():
        graph_plus_behavior = "graph_plus_behavior"
        target_relevant_excluded_uids = list(stats["target_relevant_excluded_uids"])
        if len(target_relevant_excluded_uids) >= 2:
            findings.append(
                {
                    "finding_id": f"repeated_exclusion:{sender_node_id}",
                    "graph_signal_type": "repeated_exclusion",
                    "confidence": "medium",
                    "evidence_basis": graph_plus_behavior,
                    "summary": (
                        "Same sender repeatedly sends target-relevant messages while the target remains absent "
                        "from visible recipients."
                    ),
                    "evidence_chain": {
                        "sender_node_id": sender_node_id,
                        "message_uids": target_relevant_excluded_uids,
                        "thread_group_ids": sorted(stats["threads_excluded"]),
                        "subject_families": sorted(stats["excluded_subject_families"]),
                    },
                    "counter_indicators": [
                        "Recipient omission may still have a neutral operational explanation without broader case context.",
                    ],
                }
            )
        if stats["included_uids"] and target_relevant_excluded_uids:
            findings.append(
                {
                    "finding_id": f"visibility_asymmetry:{sender_node_id}",
                    "graph_signal_type": "visibility_asymmetry",
                    "confidence": "medium",
                    "evidence_basis": "graph_only",
                    "summary": (
                        "Same sender shows mixed visibility patterns, sometimes "
                        "including the target and sometimes excluding them."
                    ),
                    "evidence_chain": {
                        "sender_node_id": sender_node_id,
                        "included_uids": list(stats["included_uids"]),
                        "excluded_uids": target_relevant_excluded_uids,
                        "subject_families": sorted(stats["included_subject_families"] | stats["excluded_subject_families"]),
                    },
                    "counter_indicators": [
                        "Different recipient sets may reflect different process stages rather than hostile exclusion.",
                    ],
                }
            )
        if stats["decision_excluded_uids"] and stats["decision_included_uids"]:
            findings.append(
                {
                    "finding_id": f"decision_visibility_asymmetry:{sender_node_id}",
                    "graph_signal_type": "decision_visibility_asymmetry",
                    "confidence": "medium",
                    "evidence_basis": graph_plus_behavior,
                    "summary": (
                        "The same sender shows decision or update handling both with and without the target "
                        "visible on the recipient list."
                    ),
                    "evidence_chain": {
                        "sender_node_id": sender_node_id,
                        "included_uids": list(stats["decision_included_uids"]),
                        "excluded_uids": list(stats["decision_excluded_uids"]),
                        "subject_families": sorted(stats["decision_subject_families"]),
                    },
                    "counter_indicators": [
                        "Decision-flow visibility can change for neutral workflow or need-to-know reasons.",
                    ],
                }
            )
        if len(stats["escalated_uids"]) >= 1 and stats["included_uids"]:
            findings.append(
                {
                    "finding_id": f"selective_escalation:{sender_node_id}",
                    "graph_signal_type": "selective_escalation",
                    "confidence": "low",
                    "evidence_basis": graph_plus_behavior,
                    "summary": "Same sender uses multi-recipient escalation or correction patterns in target-related messages.",
                    "evidence_chain": {
                        "sender_node_id": sender_node_id,
                        "message_uids": list(stats["escalated_uids"]),
                    },
                    "counter_indicators": [
                        "Broader recipient visibility may be required for operational escalation or recordkeeping.",
                    ],
                }
            )
        if stats["escalated_included_uids"] and stats["escalated_excluded_uids"]:
            findings.append(
                {
                    "finding_id": f"escalation_visibility_asymmetry:{sender_node_id}",
                    "graph_signal_type": "escalation_visibility_asymmetry",
                    "confidence": "medium",
                    "evidence_basis": graph_plus_behavior,
                    "summary": (
                        "The same sender shows escalation or public-correction messages both with and without "
                        "the target visible, creating a visibility asymmetry around escalation."
                    ),
                    "evidence_chain": {
                        "sender_node_id": sender_node_id,
                        "included_uids": list(stats["escalated_included_uids"]),
                        "excluded_uids": list(stats["escalated_excluded_uids"]),
                    },
                    "counter_indicators": [
                        "Escalation routing can legitimately vary with audience, responsibility, or recordkeeping needs.",
                    ],
                }
            )
        shared_threads = sorted(stats["threads_included"] & stats["threads_excluded"])
        if shared_threads:
            findings.append(
                {
                    "finding_id": f"forked_side_channel:{sender_node_id}",
                    "graph_signal_type": "forked_side_channel",
                    "confidence": "low",
                    "evidence_basis": "graph_only",
                    "summary": "Same sender shows both included and excluded target communication within the same thread group.",
                    "evidence_chain": {
                        "sender_node_id": sender_node_id,
                        "thread_group_ids": shared_threads,
                    },
                    "counter_indicators": [
                        "Separate recipient lists within one thread can still be operationally justified.",
                    ],
                }
            )
        fork_threads = []
        fork_uids: list[str] = []
        for thread_key, visibility in stats["thread_visibility"].items():
            if visibility["included_uids"] and visibility["target_relevant_excluded_uids"]:
                if thread_key and not thread_key.startswith("uid:"):
                    fork_threads.append(thread_key)
                for uid in [*visibility["included_uids"], *visibility["target_relevant_excluded_uids"]]:
                    if uid and uid not in fork_uids:
                        fork_uids.append(uid)
        if fork_threads:
            findings.append(
                {
                    "finding_id": f"thread_fork_exclusion:{sender_node_id}",
                    "graph_signal_type": "thread_fork_exclusion",
                    "confidence": "medium",
                    "evidence_basis": graph_plus_behavior,
                    "summary": (
                        "Within the same thread group, the sender forks target-relevant discussion into branches "
                        "where the target is no longer visible."
                    ),
                    "evidence_chain": {
                        "sender_node_id": sender_node_id,
                        "thread_group_ids": sorted(fork_threads),
                        "message_uids": fork_uids,
                    },
                    "counter_indicators": [
                        "Thread-level recipient changes can still arise from legitimate workflow splitting.",
                    ],
                }
            )

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
