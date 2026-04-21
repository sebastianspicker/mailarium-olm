"""Budgeting and evidence-packing helpers for answer context responses."""

from __future__ import annotations

import json
from typing import Any


def _compact_snippet_text(text: str, *, max_chars: int) -> str:
    """Return a compact single-line snippet."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3].rstrip() + "..."


def _evidence_identity(item: dict[str, Any]) -> str:
    """Return a stable identity key for one evidence item."""
    provenance = item.get("provenance")
    if isinstance(provenance, dict):
        handle = str(provenance.get("evidence_handle") or "")
        if handle:
            return handle
    attachment = item.get("attachment")
    attachment_name = ""
    if isinstance(attachment, dict):
        attachment_name = str(attachment.get("filename") or "")
    return "|".join(
        [
            str(item.get("uid") or ""),
            str(item.get("body_render_mode") or ""),
            attachment_name,
            str(item.get("snippet") or ""),
        ]
    )


def _dedupe_evidence_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Drop repeated evidence items while preserving the strongest first hit."""
    seen: set[str] = set()
    kept: list[dict[str, Any]] = []
    dropped = 0
    for item in items:
        key = _evidence_identity(item)
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        kept.append(item)
    return kept, dropped


def _reindex_evidence(items: list[dict[str, Any]]) -> None:
    """Rewrite evidence ranks after packing changes."""
    for index, item in enumerate(items, start=1):
        item["rank"] = index


def _is_weak_evidence_item(item: dict[str, Any]) -> bool:
    """Return whether one evidence item is weak for answer synthesis and packing."""
    if item.get("weak_message"):
        return True
    attachment = item.get("attachment")
    return isinstance(attachment, dict) and attachment.get("evidence_strength") == "weak_reference"


def _packing_priority(
    item: dict[str, Any],
    *,
    cited_candidate_uids: list[str],
) -> tuple[int, int, int, int, float, int]:
    """Return a best-evidence-first packing priority for one evidence item."""
    attachment = item.get("attachment")
    attachment_strength = ""
    if isinstance(attachment, dict):
        attachment_strength = str(attachment.get("evidence_strength") or "")
    is_weak = _is_weak_evidence_item(item)
    strength_score = 0
    if not is_weak:
        if isinstance(attachment, dict):
            if attachment_strength == "strong_text":
                strength_score = 3
            elif attachment.get("text_available"):
                strength_score = 2
            else:
                strength_score = 1
        else:
            strength_score = 3
    verification_status = str(item.get("verification_status") or "")
    exact_verified = 1 if verification_status in {"retrieval_exact", "forensic_exact", "hybrid_verified_forensic"} else 0
    forensic_verified = 1 if "forensic" in verification_status else 0
    cited = 1 if str(item.get("uid") or "") in cited_candidate_uids else 0
    score = float(item.get("score") or 0.0)
    rank = int(item.get("rank") or 0)
    return (strength_score, cited, exact_verified, forensic_verified, score, -rank)


def _weakest_evidence_target(
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
    *,
    cited_candidate_uids: list[str],
) -> tuple[str, int] | None:
    """Return the weakest current evidence item for budget-driven removal."""
    weakest: tuple[tuple[int, int, int, int, float, int], str, int] | None = None
    for kind, items in (("body", candidates), ("attachment", attachment_candidates)):
        for index, item in enumerate(items):
            candidate = (_packing_priority(item, cited_candidate_uids=cited_candidate_uids), kind, index)
            if weakest is None or candidate < weakest:
                weakest = candidate
    if weakest is None:
        return None
    return weakest[1], weakest[2]


def _snippet_budget_for_item(
    item: dict[str, Any],
    *,
    cited_candidate_uids: list[str],
    phase: str,
) -> int:
    """Return the compaction budget for one item in one packing phase."""
    priority = _packing_priority(item, cited_candidate_uids=cited_candidate_uids)
    strength_score, cited, exact_verified, forensic_verified, _score, _rank = priority
    if phase == "primary":
        if cited or exact_verified:
            return 220
        if strength_score >= 3 or forensic_verified:
            return 180
        if strength_score >= 2:
            return 140
        return 100
    if cited or exact_verified:
        return 140
    if strength_score >= 3 or forensic_verified:
        return 110
    if strength_score >= 2:
        return 80
    return 60


def _compact_snippets_for_budget(
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
    *,
    cited_candidate_uids: list[str],
    phase: str,
) -> int:
    """Compact snippets in weak-to-strong order while protecting answer-bearing evidence."""
    changes = 0
    ordered_items = sorted(
        [*candidates, *attachment_candidates],
        key=lambda item: _packing_priority(item, cited_candidate_uids=cited_candidate_uids),
    )
    for item in ordered_items:
        snippet = str(item.get("snippet") or "")
        compacted = _compact_snippet_text(
            snippet,
            max_chars=_snippet_budget_for_item(item, cited_candidate_uids=cited_candidate_uids, phase=phase),
        )
        if compacted != snippet:
            item["snippet"] = compacted
            provenance = item.get("provenance")
            if isinstance(provenance, dict):
                start = provenance.get("snippet_start")
                end = provenance.get("snippet_end")
                visible_chars = len(compacted[:-3]) if compacted.endswith("...") else len(compacted)
                if isinstance(start, int):
                    provenance["visible_excerpt_start"] = start
                    provenance["visible_excerpt_end"] = start + visible_chars
                elif isinstance(end, int):
                    provenance["visible_excerpt_end"] = min(int(end), visible_chars)
                provenance["anchored_snippet_end"] = end
                provenance["visible_excerpt_compacted"] = True
            changes += 1
    return changes


def _estimated_json_chars(payload: dict[str, Any]) -> int:
    """Return an approximate pretty-printed JSON size for the response payload."""
    return len(json.dumps(payload, indent=2, default=str))


def _compact_timeline_events(
    timeline: dict[str, Any],
    *,
    max_events: int = 5,
) -> tuple[dict[str, Any], int]:
    """Compact timeline events while keeping key anchors explicit."""
    events = timeline.get("events")
    if not isinstance(events, list) or len(events) <= max_events:
        return timeline, 0
    first_uid = str(timeline.get("first_uid") or "")
    last_uid = str(timeline.get("last_uid") or "")
    key_transition_uid = str(timeline.get("key_transition_uid") or "")
    wanted = [uid for uid in [first_uid, key_transition_uid, last_uid] if uid]
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    for uid in wanted:
        for event in events:
            event_uid = str(event.get("uid") or "")
            if event_uid == uid and event_uid not in seen:
                kept.append(event)
                seen.add(event_uid)
                break
    for event in events:
        event_uid = str(event.get("uid") or "")
        if event_uid in seen:
            continue
        if len(kept) >= max_events:
            break
        kept.append(event)
        seen.add(event_uid)
    compacted = {**timeline, "event_count": len(kept), "events": kept}
    return compacted, len(events) - len(kept)


def _summarize_timeline_for_budget(timeline: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Return a smaller timeline summary that preserves anchor events without snippets."""
    compacted, dropped = _compact_timeline_events(timeline, max_events=3)
    events = compacted.get("events")
    if not isinstance(events, list):
        return compacted, dropped
    summarized_events = [
        {
            "uid": str(event.get("uid") or ""),
            "date": str(event.get("date") or ""),
            "score": round(float(event.get("score") or 0.0), 3),
        }
        for event in events
    ]
    return {
        **compacted,
        "event_count": len(summarized_events),
        "events": summarized_events,
    }, dropped


def _summarize_conversation_groups_for_budget(groups: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Return compact conversation-group summaries for tight response budgets."""
    if not groups:
        return groups, 0
    kept: list[dict[str, Any]] = []
    for group in groups[:1]:
        kept.append(
            {
                "conversation_id": str(group.get("conversation_id") or ""),
                "inferred_thread_id": str(group.get("inferred_thread_id") or ""),
                "thread_group_id": str(group.get("thread_group_id") or ""),
                "thread_group_source": str(group.get("thread_group_source") or ""),
                "top_uid": str(group.get("top_uid") or ""),
                "message_count": int(group.get("message_count") or 0),
                "date_range": dict(group.get("date_range") or {}),
                "participants": list(group.get("participants") or [])[:2],
                "matched_uids": [str(uid) for uid in list(group.get("matched_uids") or [])[:2] if uid],
            }
        )
    return kept, max(0, len(groups) - len(kept))


def _strip_optional_evidence_fields(
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
    *,
    force_deep_candidate_analysis_strip: bool = False,
) -> int:
    """Remove optional heavy fields from evidence items and return count of changes."""
    changes = 0
    for item in [*candidates, *attachment_candidates]:
        if "conversation_context" in item:
            item.pop("conversation_context", None)
            changes += 1
        if "follow_up" in item:
            item.pop("follow_up", None)
            changes += 1
        if "thread_graph" in item:
            item.pop("thread_graph", None)
            changes += 1
        if "sender_name" in item:
            item.pop("sender_name", None)
            changes += 1
        if "conversation_id" in item:
            item.pop("conversation_id", None)
            changes += 1
    for candidate in candidates:
        removable_fields = ["body_render_mode", "body_render_source", "verification_status", "speaker_attribution"]
        if force_deep_candidate_analysis_strip:
            removable_fields.extend(["language_rhetoric", "message_findings", "reply_pairing"])
        for field in removable_fields:
            if field in candidate:
                candidate.pop(field, None)
                changes += 1
    for attachment_candidate in attachment_candidates:
        attachment = attachment_candidate.get("attachment")
        if isinstance(attachment, dict):
            compact_attachment = {
                "filename": attachment.get("filename"),
                "extraction_state": attachment.get("extraction_state"),
            }
            if compact_attachment != attachment:
                attachment_candidate["attachment"] = compact_attachment
                changes += 1
    return changes
