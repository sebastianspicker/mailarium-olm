"""Answer-context helpers extracted from ``src.tools.search``."""

from __future__ import annotations

import json
import re
from typing import Any

from ..actor_resolution import resolve_actor_graph, resolve_actor_id
from ..behavioral_evidence_chains import build_behavioral_evidence_chains
from ..behavioral_strength import apply_behavioral_strength
from ..behavioral_taxonomy import behavioral_taxonomy_payload
from ..case_intake import build_case_bundle
from ..communication_graph import build_communication_graph
from ..comparative_treatment import build_comparative_treatment
from ..cross_message_patterns import build_case_patterns
from ..formatting import resolve_body_for_render, weak_message_semantics
from ..investigation_report import build_investigation_report, compact_investigation_report
from ..language_rhetoric import LANGUAGE_RHETORIC_VERSION, analyze_message_rhetoric
from ..mcp_models import EmailAnswerContextInput
from ..message_behavior import MESSAGE_BEHAVIOR_VERSION, analyze_message_behavior
from ..multi_source_case_bundle import build_multi_source_case_bundle
from ..power_context import apply_power_context_to_actor_graph, build_power_context
from ..reply_context import extract_reply_context
from ..trigger_retaliation import build_retaliation_analysis
from .utils import ToolDepsProto, json_response

_ATTACHMENT_HEADER_RE = re.compile(r'^\[Attachment:\s*(.+?)\s+from email\s+"', re.IGNORECASE)
_EMAIL_CANDIDATE_RE = re.compile(r"(?i)(?:mailto:)?([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})")
_FROM_HEADER_RE = re.compile(r"(?im)^from:\s*(.+)$")


def _answer_context_search_kwargs(params: EmailAnswerContextInput, top_k: int) -> dict[str, Any]:
    """Build ``search_filtered`` kwargs for the answer-context tool."""
    kwargs: dict[str, Any] = {
        "query": params.question,
        "top_k": top_k,
    }
    if params.sender is not None:
        kwargs["sender"] = params.sender
    if params.subject is not None:
        kwargs["subject"] = params.subject
    if params.folder is not None:
        kwargs["folder"] = params.folder
    if params.has_attachments is not None:
        kwargs["has_attachments"] = params.has_attachments
    if params.email_type is not None:
        kwargs["email_type"] = params.email_type
    if params.date_from is not None:
        kwargs["date_from"] = params.date_from
    elif params.case_scope is not None and params.case_scope.date_from is not None:
        kwargs["date_from"] = params.case_scope.date_from
    if params.date_to is not None:
        kwargs["date_to"] = params.date_to
    elif params.case_scope is not None and params.case_scope.date_to is not None:
        kwargs["date_to"] = params.case_scope.date_to
    if params.rerank:
        kwargs["rerank"] = True
    if params.hybrid:
        kwargs["hybrid"] = True
    return kwargs


def _snippet(text: str, *, max_chars: int = 280) -> str:
    """Return a compact single-line snippet for answer evidence."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 3].rstrip() + "..."


def _match_reason(rank: int, params: EmailAnswerContextInput) -> str:
    """Return a compact explanation for why a candidate was included."""
    parts = ["Top-ranked semantic match" if rank == 1 else "High-ranked semantic match"]
    if params.hybrid:
        parts.append("hybrid recall enabled")
    if params.rerank:
        parts.append("reranked for precision")
    return "; ".join(parts) + "."


def _verified_snippet_for_mode(body_text: str, retrieval_snippet: str) -> tuple[str, str, int | None, int | None]:
    """Return snippet, verification status, and bounds for the requested body text."""
    start, end = _find_snippet_bounds(body_text, retrieval_snippet)
    if start is not None and end is not None:
        return body_text[start:end], "exact", start, end
    fallback = _snippet(body_text) if body_text else retrieval_snippet
    if not fallback:
        fallback = retrieval_snippet
    start, end = _find_snippet_bounds(body_text, fallback)
    return fallback, "fallback", start, end


def _find_snippet_bounds(body_text: str, snippet: str) -> tuple[int | None, int | None]:
    """Locate *snippet* in *body_text*, tolerating collapsed whitespace."""
    if not body_text or not snippet:
        return None, None
    exact_start = body_text.find(snippet)
    if exact_start >= 0:
        return exact_start, exact_start + len(snippet)

    body_chars: list[str] = []
    body_map: list[int] = []
    prev_space = False
    for idx, char in enumerate(body_text):
        if char.isspace():
            if prev_space:
                continue
            body_chars.append(" ")
            body_map.append(idx)
            prev_space = True
        else:
            body_chars.append(char)
            body_map.append(idx)
            prev_space = False
    normalized_body = "".join(body_chars)
    normalized_snippet = " ".join(snippet.split())
    collapsed_start = normalized_body.find(normalized_snippet)
    if collapsed_start < 0:
        return None, None
    start = body_map[collapsed_start]
    end = body_map[collapsed_start + len(normalized_snippet) - 1] + 1
    return start, end


def _segment_ordinal_for_snippet(db: Any, uid: str, snippet: str) -> int | None:
    """Return the first segment ordinal containing *snippet*, if available."""
    conn = getattr(db, "conn", None)
    if conn is None:
        return None
    rows = conn.execute(
        """SELECT ordinal, text
           FROM message_segments
           WHERE email_uid = ?
           ORDER BY ordinal ASC""",
        (uid,),
    ).fetchall()
    normalized_snippet = " ".join(snippet.split())
    for row in rows:
        segment_text = row["text"] if not isinstance(row, dict) else row.get("text", "")
        if not segment_text:
            continue
        if snippet in segment_text or normalized_snippet in " ".join(segment_text.split()):
            ordinal = row["ordinal"] if not isinstance(row, dict) else row.get("ordinal")
            return int(ordinal) if ordinal is not None else None
    return None


def _is_attachment_result(metadata: dict[str, Any], *, chunk_id: str = "") -> bool:
    """Return whether a search result represents attachment-derived evidence."""
    raw_flag = metadata.get("is_attachment")
    if isinstance(raw_flag, str):
        if raw_flag.lower() == "true":
            return True
    elif raw_flag:
        return True
    if metadata.get("attachment_filename"):
        return True
    if str(metadata.get("chunk_type") or "").lower() == "image":
        return True
    return "__att_" in chunk_id or "__img_" in chunk_id


def _attachment_extraction_state(metadata: dict[str, Any], *, chunk_id: str = "") -> str | None:
    """Return best-effort attachment extraction state from existing chunk metadata."""
    explicit = metadata.get("extraction_state")
    if explicit:
        return str(explicit).strip().lower()
    if str(metadata.get("chunk_type") or "").lower() == "image":
        return "image_embedding_only"
    if _is_attachment_result(metadata, chunk_id=chunk_id):
        return "text_extracted"
    return None


def _attachment_evidence_profile(
    metadata: dict[str, Any],
    *,
    chunk_id: str = "",
    snippet: str = "",
) -> dict[str, Any]:
    """Return normalized attachment evidence semantics for answer-facing output."""
    extraction_state = _attachment_extraction_state(metadata, chunk_id=chunk_id) or ""
    normalized = extraction_state.strip().lower()
    normalized_snippet = " ".join((snippet or "").split())
    weak_reference_only = bool(_ATTACHMENT_HEADER_RE.match((snippet or "").strip())) and "\n" not in (snippet or "")

    if normalized in {"ocr_text_extracted", "ocr_extracted_text", "ocr_success"}:
        extraction_state = "ocr_text_extracted"
        text_available = True
        ocr_used = True
        failure_reason = None
        evidence_strength = "strong_text"
    elif normalized in {"text_extracted", "text"}:
        extraction_state = "binary_only" if weak_reference_only else "text_extracted"
        text_available = not weak_reference_only
        ocr_used = False
        failure_reason = None if text_available else "no_text_extracted"
        evidence_strength = "strong_text" if text_available else "weak_reference"
    elif normalized in {"ocr_failed", "ocr_failure"}:
        extraction_state = "ocr_failed"
        text_available = False
        ocr_used = True
        failure_reason = "ocr_failed"
        evidence_strength = "weak_reference"
    elif normalized in {"extraction_failed", "text_extraction_failed"}:
        extraction_state = "extraction_failed"
        text_available = False
        ocr_used = False
        failure_reason = "extraction_failed"
        evidence_strength = "weak_reference"
    elif normalized in {"binary_only", "image_embedding_only", "image_only_no_text"}:
        extraction_state = "binary_only"
        text_available = False
        ocr_used = normalized.startswith("ocr_")
        failure_reason = "no_text_extracted"
        evidence_strength = "weak_reference"
    else:
        extraction_state = normalized or "unknown"
        text_available = bool(normalized_snippet)
        ocr_used = "ocr" in extraction_state
        failure_reason = None if text_available else "unknown"
        evidence_strength = "strong_text" if text_available else "weak_reference"

    return {
        "extraction_state": extraction_state,
        "text_available": text_available,
        "ocr_used": ocr_used,
        "failure_reason": failure_reason,
        "evidence_strength": evidence_strength,
    }


def _attachment_record_for_candidate(db: Any, uid: str, filename: str) -> dict[str, Any] | None:
    """Return the matching attachment record for one candidate, if the DB exposes it."""
    if not db or not uid or not filename or not hasattr(db, "attachments_for_email"):
        return None
    attachments = db.attachments_for_email(uid)
    for attachment in attachments:
        if str(attachment.get("name") or "") == filename:
            return attachment
    return None


def _attachment_candidate(
    db: Any,
    result: Any,
    *,
    rank: int,
    params: EmailAnswerContextInput,
) -> dict[str, Any]:
    """Build one attachment evidence candidate from a search result."""
    metadata = result.metadata
    uid = str(metadata.get("uid", ""))
    filename = str(metadata.get("attachment_filename") or metadata.get("filename") or "")
    if not filename:
        header_match = _ATTACHMENT_HEADER_RE.match(result.text.strip())
        if header_match:
            filename = header_match.group(1).strip()
    if not filename:
        filename = "attachment"
    snippet = _snippet(result.text)
    snippet_start = 0
    snippet_end = len(snippet)
    record = _attachment_record_for_candidate(db, uid, filename)
    evidence_profile = _attachment_evidence_profile(metadata, chunk_id=result.chunk_id, snippet=result.text)
    attachment_info = {
        "filename": filename,
        "mime_type": (record or {}).get("mime_type"),
        "size": (record or {}).get("size"),
        "content_id": (record or {}).get("content_id"),
        "is_inline": bool((record or {}).get("is_inline", False)) if record is not None else None,
        **evidence_profile,
    }
    provenance = {
        "evidence_handle": f"attachment:{uid}:{filename}:{result.chunk_id}:{snippet_start}:{snippet_end}",
        "uid": uid,
        "chunk_id": result.chunk_id,
        "snippet_start": snippet_start,
        "snippet_end": snippet_end,
        "attachment_filename": filename,
    }
    return {
        "rank": rank,
        "uid": uid,
        "subject": metadata.get("subject", ""),
        "sender_email": metadata.get("sender_email", ""),
        "sender_name": metadata.get("sender_name", ""),
        "date": metadata.get("date", ""),
        "conversation_id": metadata.get("conversation_id", ""),
        "score": result.score,
        "snippet": snippet,
        "match_reason": _match_reason(rank, params),
        "attachment": attachment_info,
        "provenance": provenance,
        "follow_up": {
            "tool": "email_deep_context",
            "uid": uid,
        },
    }


def _conversation_group_summaries(
    db: Any,
    *,
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Build ranked conversation-group summaries for the current answer bundle."""
    grouped: dict[str, dict[str, Any]] = {}
    ordered_candidates = [*candidates, *attachment_candidates]
    for candidate in ordered_candidates:
        thread_group_id = str(candidate.get("thread_group_id") or "")
        if not thread_group_id:
            continue
        conversation_id = str(candidate.get("conversation_id") or "")
        inferred_thread_id = str(candidate.get("inferred_thread_id") or "")
        thread_group_source = str(candidate.get("thread_group_source") or "canonical")
        group = grouped.get(thread_group_id)
        score = float(candidate.get("score") or 0.0)
        uid = str(candidate.get("uid") or "")
        if group is None:
            group = {
                "conversation_id": conversation_id,
                "inferred_thread_id": inferred_thread_id,
                "thread_group_id": thread_group_id,
                "thread_group_source": thread_group_source,
                "top_uid": uid,
                "top_score": score,
                "matched_uids": [],
                "participants": [],
                "date_range": {},
                "message_count": 0,
            }
            grouped[thread_group_id] = group
        if uid and uid not in group["matched_uids"]:
            group["matched_uids"].append(uid)
        if score > float(group["top_score"]):
            group["top_score"] = score
            group["top_uid"] = uid

    for _thread_group_id, group in grouped.items():
        thread_emails: list[dict[str, Any]] = []
        if db:
            if group["thread_group_source"] == "canonical" and hasattr(db, "get_thread_emails"):
                thread_emails = db.get_thread_emails(str(group["conversation_id"] or "")) or []
            elif group["thread_group_source"] == "inferred" and hasattr(db, "get_inferred_thread_emails"):
                thread_emails = db.get_inferred_thread_emails(str(group["inferred_thread_id"] or "")) or []
            elif hasattr(db, "get_thread_emails") and group["conversation_id"]:
                thread_emails = db.get_thread_emails(str(group["conversation_id"] or "")) or []
        if thread_emails:
            participants = sorted({str(email.get("sender_email") or "") for email in thread_emails if email.get("sender_email")})
            dates = sorted(str(email.get("date") or "")[:10] for email in thread_emails if email.get("date"))
            group["participants"] = participants
            group["message_count"] = len(thread_emails)
            if dates:
                group["date_range"] = {"first": dates[0], "last": dates[-1]}
            else:
                group["date_range"] = {}
        else:
            group["message_count"] = len(group["matched_uids"])

    conversation_groups = sorted(grouped.values(), key=lambda item: float(item["top_score"]), reverse=True)
    by_id = {group["thread_group_id"]: group for group in conversation_groups}
    return conversation_groups, by_id


def _attach_conversation_context(
    items: list[dict[str, Any]],
    conversation_group_by_id: dict[str, dict[str, Any]],
) -> None:
    """Attach current conversation summaries to evidence items."""
    for item in items:
        thread_group_id = str(item.get("thread_group_id") or "")
        if thread_group_id and thread_group_id in conversation_group_by_id:
            item["conversation_context"] = conversation_group_by_id[thread_group_id]
        else:
            item.pop("conversation_context", None)


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
    exact_verified = 1 if verification_status in {"forensic_exact", "hybrid_verified_forensic"} else 0
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
        compacted = _snippet(
            snippet,
            max_chars=_snippet_budget_for_item(item, cited_candidate_uids=cited_candidate_uids, phase=phase),
        )
        if compacted != snippet:
            item["snippet"] = compacted
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
        for field in ("body_render_mode", "body_render_source", "verification_status", "speaker_attribution"):
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


def _answer_quality(
    *,
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
    conversation_groups: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a compact confidence and ambiguity summary for the answer bundle."""
    ordered = sorted([*candidates, *attachment_candidates], key=lambda item: float(item.get("score") or 0.0), reverse=True)
    if not ordered:
        return {
            "confidence_label": "low",
            "confidence_score": 0.0,
            "ambiguity_reason": "no_evidence",
            "alternative_candidates": [],
            "top_candidate_uid": "",
            "top_conversation_id": "",
            "top_thread_group_id": "",
            "top_thread_group_source": "",
        }

    top = ordered[0]
    top_score = float(top.get("score") or 0.0)
    second_score = float(ordered[1].get("score") or 0.0) if len(ordered) > 1 else 0.0
    gap = top_score - second_score
    ambiguity_reason = ""
    confidence_label = "medium"

    if len(ordered) > 1 and gap <= 0.03:
        confidence_label = "ambiguous"
        ambiguity_reason = "close_top_scores"
    elif top_score >= 0.85 and gap >= 0.15:
        confidence_label = "high"
    elif top_score < 0.6:
        confidence_label = "low"
        ambiguity_reason = "weak_top_score"

    alternative_candidates = [str(item.get("uid") or "") for item in ordered[1:3] if item.get("uid")]
    if confidence_label == "high":
        alternative_candidates = []

    top_conversation_id = ""
    top_thread_group_id = ""
    top_thread_group_source = ""
    if conversation_groups:
        top_conversation_id = str(conversation_groups[0].get("conversation_id") or "")
        top_thread_group_id = str(conversation_groups[0].get("thread_group_id") or "")
        top_thread_group_source = str(conversation_groups[0].get("thread_group_source") or "")
    elif top.get("conversation_id"):
        top_conversation_id = str(top.get("conversation_id") or "")
        top_thread_group_id = top_conversation_id
        top_thread_group_source = "canonical"
    elif top.get("inferred_thread_id"):
        top_thread_group_id = str(top.get("inferred_thread_id") or "")
        top_thread_group_source = "inferred"

    return {
        "confidence_label": confidence_label,
        "confidence_score": round(top_score, 3),
        "ambiguity_reason": ambiguity_reason,
        "alternative_candidates": alternative_candidates,
        "top_candidate_uid": str(top.get("uid") or ""),
        "top_conversation_id": top_conversation_id,
        "top_thread_group_id": top_thread_group_id,
        "top_thread_group_source": top_thread_group_source,
    }


def _question_requests_exact_wording(question: str) -> bool:
    """Return whether the question likely needs exact wording verification."""
    normalized = question.lower()
    markers = (
        "exactly",
        "exact wording",
        "what did",
        "quote",
        "quoted",
        "verbatim",
    )
    return any(marker in normalized for marker in markers)


def _has_weak_evidence(
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
) -> bool:
    """Return whether the current evidence bundle is dominated by weak-message cases."""
    return any(_is_weak_evidence_item(item) for item in [*candidates, *attachment_candidates])


def _answer_policy(
    *,
    question: str,
    evidence_mode: str,
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
    answer_quality: dict[str, Any],
) -> dict[str, Any]:
    """Return deterministic answer-synthesis guidance for downstream callers."""
    confidence_label = str(answer_quality.get("confidence_label") or "low")
    ambiguity_reason = str(answer_quality.get("ambiguity_reason") or "")
    top_candidate_uid = str(answer_quality.get("top_candidate_uid") or "")
    alternative_candidates = [str(uid) for uid in answer_quality.get("alternative_candidates", []) if uid]
    exact_wording = _question_requests_exact_wording(question)
    weak_evidence = _has_weak_evidence(candidates, attachment_candidates)
    verification_mode = "already_forensic" if evidence_mode == "forensic" else "retrieval_ok"
    if evidence_mode != "forensic" and (exact_wording or confidence_label in {"ambiguous", "medium"} or weak_evidence):
        verification_mode = "verify_forensic"

    if confidence_label == "ambiguous":
        decision = "ambiguous"
    elif confidence_label == "low" or ambiguity_reason in {"no_evidence", "weak_top_score", "weak_scan_body"} or weak_evidence:
        decision = "insufficient_evidence"
    else:
        decision = "answer"

    cite_candidate_uids = [uid for uid in [top_candidate_uid, *alternative_candidates] if uid]
    max_citations = 1
    if decision == "ambiguous":
        max_citations = min(2, max(len(cite_candidate_uids), 1))
    elif decision == "insufficient_evidence" and cite_candidate_uids:
        max_citations = 1

    if decision == "answer" and confidence_label == "high":
        confidence_phrase = "The evidence strongly indicates"
    elif decision == "answer":
        confidence_phrase = "The available evidence suggests"
    else:
        confidence_phrase = "The available evidence is limited"

    return {
        "decision": decision,
        "verification_mode": verification_mode,
        "max_citations": max_citations,
        "cite_candidate_uids": cite_candidate_uids[:max_citations],
        "confidence_phrase": confidence_phrase,
        "ambiguity_phrase": "The available evidence is ambiguous",
        "fallback_phrase": (
            "I can identify the likely message, but the available evidence is too weak to state the content confidently."
        ),
        "refuse_to_overclaim": True,
    }


def _final_answer_contract(*, answer_policy: dict[str, Any]) -> dict[str, Any]:
    """Return the outward response contract for mailbox answers."""
    decision = str(answer_policy.get("decision") or "insufficient_evidence")
    cite_candidate_uids = [str(uid) for uid in answer_policy.get("cite_candidate_uids", []) if uid]
    if decision == "ambiguous":
        answer_shape = "two_short_paragraphs"
    else:
        answer_shape = "single_paragraph"
    return {
        "decision": decision,
        "answer_format": {
            "shape": answer_shape,
            "cite_at_sentence_end": True,
            "max_citations": int(answer_policy.get("max_citations") or 0),
            "include_confidence_wording": decision == "answer",
            "include_ambiguity_wording": decision == "ambiguous",
            "include_fallback_wording": decision == "insufficient_evidence",
        },
        "citation_format": {
            "style": "inline_uid_brackets",
            "pattern": "[uid:<EMAIL_UID>]",
            "required_attribution": "Only cite UIDs from required_citation_uids.",
        },
        "confidence_wording": str(answer_policy.get("confidence_phrase") or ""),
        "ambiguity_wording": str(answer_policy.get("ambiguity_phrase") or ""),
        "fallback_wording": str(answer_policy.get("fallback_phrase") or ""),
        "required_citation_uids": cite_candidate_uids,
        "verification_mode": str(answer_policy.get("verification_mode") or ""),
        "refuse_to_overclaim": bool(answer_policy.get("refuse_to_overclaim", True)),
    }


def _uid_citation(uid: str) -> str:
    """Return one inline UID citation token."""
    return f"[uid:{uid}]"


def _ordered_evidence(
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return answer evidence ordered by score descending."""
    return sorted([*candidates, *attachment_candidates], key=lambda item: float(item.get("score") or 0.0), reverse=True)


def _evidence_description(item: dict[str, Any]) -> str:
    """Return a short human-readable description of one evidence item."""
    subject = str(item.get("subject") or "").strip()
    date = str(item.get("date") or "").strip()
    attachment = item.get("attachment")
    if isinstance(attachment, dict):
        filename = str(attachment.get("filename") or "attachment").strip()
        base = f'the attachment "{filename}"'
        if subject:
            base += f' in "{subject}"'
        if date:
            base += f" from {date[:10]}"
    else:
        if subject:
            base = f'the message "{subject}"'
        else:
            base = "the strongest matching message"
        if date:
            base += f" from {date[:10]}"
    return base


def _render_final_answer(
    *,
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
    answer_policy: dict[str, Any],
    final_answer_contract: dict[str, Any],
) -> dict[str, Any]:
    """Render a deterministic final mailbox answer from the current evidence bundle."""
    ordered = _ordered_evidence(candidates, attachment_candidates)
    decision = str(answer_policy.get("decision") or final_answer_contract.get("decision") or "insufficient_evidence")
    required_citation_uids = [str(uid) for uid in final_answer_contract.get("required_citation_uids", []) if uid]
    citations = [_uid_citation(uid) for uid in required_citation_uids]
    citation_text = " ".join(citations)
    top_item = ordered[0] if ordered else None

    if decision == "ambiguous":
        cited_items = [item for item in ordered if str(item.get("uid") or "") in required_citation_uids][:2]
        ambiguity_wording = str(final_answer_contract.get("ambiguity_wording") or answer_policy.get("ambiguity_phrase") or "")
        first = ambiguity_wording or "The available evidence is ambiguous."
        if not first.endswith("."):
            first += "."
        descriptions = [_evidence_description(item) for item in cited_items]
        if descriptions:
            second = "The strongest candidates are " + " and ".join(descriptions) + "."
        else:
            second = "The strongest candidates remain too close to support one confident answer."
        if citation_text:
            second = f"{second} {citation_text}"
        text = f"{first}\n\n{second}"
    elif decision == "answer":
        confidence = str(final_answer_contract.get("confidence_wording") or answer_policy.get("confidence_phrase") or "").strip()
        if top_item is None:
            text = "No answer-bearing evidence is available."
        else:
            description = _evidence_description(top_item)
            prefix = confidence or "The available evidence suggests"
            sentence = f"{prefix} {description}."
            text = f"{sentence} {citation_text}".strip()
    else:
        fallback = str(final_answer_contract.get("fallback_wording") or answer_policy.get("fallback_phrase") or "").strip()
        if not fallback:
            fallback = (
                "I can identify the likely message, but the available evidence is too weak to state the content confidently."
            )
        if top_item is not None:
            description = _evidence_description(top_item)
            text = f"{fallback} The strongest candidate is {description}."
            if citation_text:
                text = f"{text} {citation_text}"
        else:
            text = fallback

    return {
        "decision": decision,
        "text": text.strip(),
        "citations": required_citation_uids,
        "verification_mode": str(final_answer_contract.get("verification_mode") or answer_policy.get("verification_mode") or ""),
        "answer_shape": str((final_answer_contract.get("answer_format") or {}).get("shape") or ""),
    }


def _timeline_summary(
    *,
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a chronological summary for process-style questions."""
    dated_items = [item for item in [*candidates, *attachment_candidates] if str(item.get("date") or "").strip()]
    ordered = sorted(dated_items, key=lambda item: (str(item.get("date") or ""), str(item.get("uid") or "")))
    events: list[dict[str, Any]] = []
    for item in ordered:
        events.append(
            {
                "uid": str(item.get("uid") or ""),
                "date": str(item.get("date") or ""),
                "conversation_id": str(item.get("conversation_id") or ""),
                "score": round(float(item.get("score") or 0.0), 3),
                "snippet": str(item.get("snippet") or ""),
            }
        )
    if not events:
        return {
            "event_count": 0,
            "date_range": {},
            "first_uid": "",
            "last_uid": "",
            "key_transition_uid": "",
            "events": [],
        }

    first_uid = events[0]["uid"]
    last_uid = events[-1]["uid"]
    key_transition_uid = str(max(events, key=lambda event: float(event.get("score") or 0.0)).get("uid") or "")
    return {
        "event_count": len(events),
        "date_range": {"first": str(events[0].get("date") or "")[:10], "last": str(events[-1].get("date") or "")[:10]},
        "first_uid": first_uid,
        "last_uid": last_uid,
        "key_transition_uid": key_transition_uid,
        "events": events,
    }


def _segment_rows_for_uid(db: Any, uid: str) -> list[dict[str, Any]]:
    """Return persisted conversation segments for one email, if available."""
    conn = getattr(db, "conn", None)
    if conn is None or not uid:
        return []
    rows = conn.execute(
        """SELECT ordinal, segment_type, depth, text, source_surface
           FROM message_segments
           WHERE email_uid = ?
           ORDER BY ordinal ASC""",
        (uid,),
    ).fetchall()
    return [dict(row) if not isinstance(row, dict) else row for row in rows]


def _normalize_attributed_email(value: str) -> str:
    """Return a best-effort normalized email address for attribution output."""
    normalized = value.strip().lower()
    if not normalized:
        return ""
    match = _EMAIL_CANDIDATE_RE.search(normalized)
    if match:
        return match.group(1).lower()
    return normalized


def _quoted_block_candidates(segment_text: str, authored_email: str) -> list[str]:
    """Return unique non-authored email candidates visible in one quoted block."""
    candidates: list[str] = []
    for match in _EMAIL_CANDIDATE_RE.finditer(segment_text or ""):
        email = _normalize_attributed_email(match.group(0))
        if not email or email == authored_email:
            continue
        if email not in candidates:
            candidates.append(email)
    return candidates


def _quoted_from_header_candidate(segment_text: str, authored_email: str) -> str:
    """Return one quoted speaker email from a visible ``From:`` header, if unambiguous."""
    match = _FROM_HEADER_RE.search(segment_text or "")
    if not match:
        return ""
    candidates = _quoted_block_candidates(match.group(1), authored_email)
    if len(candidates) == 1:
        return candidates[0]
    return ""


def _reply_context_identities(full_email: dict[str, Any] | None, authored_email: str) -> tuple[str, list[str]]:
    """Return normalized reply-context identities excluding the authored speaker."""
    normalized_authored_email = authored_email.strip().lower()
    reply_context_from = _normalize_attributed_email(str((full_email or {}).get("reply_context_from") or ""))
    reply_context_to = [
        _normalize_attributed_email(identity)
        for identity in ((full_email or {}).get("reply_context_to") or [])
        if identity
    ]
    identities = [
        identity
        for identity in [reply_context_from, *reply_context_to]
        if identity and identity != normalized_authored_email
    ]
    return reply_context_from, list(dict.fromkeys(identities))


def _quoted_reply_context_identities(segment_text: str, authored_email: str) -> list[str]:
    """Return unique quoted reply-context identities visible in one segment."""
    normalized_authored_email = authored_email.strip().lower()
    quoted_reply_context = extract_reply_context(segment_text, "", "reply")
    if not quoted_reply_context or not quoted_reply_context.from_email:
        return []
    quoted_from = _normalize_attributed_email(quoted_reply_context.from_email)
    quoted_to = [_normalize_attributed_email(identity) for identity in quoted_reply_context.to_emails]
    reply_context_identities = [
        identity for identity in [quoted_from, *quoted_to] if identity and identity != normalized_authored_email
    ]
    return list(dict.fromkeys(reply_context_identities))


def _quote_attribution_details(
    *,
    full_email: dict[str, Any] | None,
    authored_email: str,
    conversation_context: dict[str, Any] | None,
    segment_text: str = "",
) -> dict[str, Any]:
    """Return one normalized quote-attribution decision with explicit ambiguity state."""
    normalized_authored_email = authored_email.strip().lower()
    quoted_from_header = _quoted_from_header_candidate(segment_text, normalized_authored_email)
    quoted_reply_context_identities = _quoted_reply_context_identities(segment_text, normalized_authored_email)
    quoted_block_emails = _quoted_block_candidates(segment_text, normalized_authored_email)
    reply_context_from, reply_context_identities = _reply_context_identities(full_email, normalized_authored_email)

    if quoted_from_header:
        return {
            "speaker_email": quoted_from_header,
            "source": "quoted_from_header",
            "confidence": 0.85,
            "quote_attribution_status": "explicit_header",
            "quote_attribution_reason": "",
            "candidate_emails": [quoted_from_header],
            "downgraded_due_to_quote_ambiguity": False,
        }
    if len(quoted_reply_context_identities) == 1:
        speaker_email = quoted_reply_context_identities[0]
        if reply_context_from and reply_context_from == speaker_email:
            return {
                "speaker_email": speaker_email,
                "source": "reply_context_from_corroborated",
                "confidence": 0.8,
                "quote_attribution_status": "corroborated_reply_context",
                "quote_attribution_reason": "",
                "candidate_emails": [speaker_email],
                "downgraded_due_to_quote_ambiguity": False,
            }
        return {
            "speaker_email": speaker_email,
            "source": "quoted_block_reply_context",
            "confidence": 0.72,
            "quote_attribution_status": "corroborated_reply_context",
            "quote_attribution_reason": "",
            "candidate_emails": [speaker_email],
            "downgraded_due_to_quote_ambiguity": False,
        }
    if len(quoted_block_emails) == 1:
        speaker_email = quoted_block_emails[0]
        status = "inferred_single_candidate"
        confidence = 0.6
        source = "quoted_block_email"
        if reply_context_from and reply_context_from == speaker_email:
            status = "corroborated_reply_context"
            confidence = 0.78
            source = "reply_context_from_corroborated"
        return {
            "speaker_email": speaker_email,
            "source": source,
            "confidence": confidence,
            "quote_attribution_status": status,
            "quote_attribution_reason": (
                ""
                if status == "corroborated_reply_context"
                else "Only one non-authored identity is visible in the quoted block, so ownership remains inferred."
            ),
            "candidate_emails": quoted_block_emails,
            "downgraded_due_to_quote_ambiguity": status != "corroborated_reply_context",
        }
    participants = []
    if conversation_context:
        participants = [
            str(participant).strip().lower() for participant in conversation_context.get("participants", []) if participant
        ]
    alternatives = [participant for participant in participants if participant and participant != normalized_authored_email]
    unique_alternatives = list(dict.fromkeys(alternatives))
    if len(unique_alternatives) == 1:
        return {
            "speaker_email": unique_alternatives[0],
            "source": "conversation_participant_exclusion",
            "confidence": 0.5,
            "quote_attribution_status": "participant_exclusion",
            "quote_attribution_reason": (
                "Quoted ownership is inferred only from the remaining conversation participants, so it should be read cautiously."
            ),
            "candidate_emails": unique_alternatives,
            "downgraded_due_to_quote_ambiguity": True,
        }
    return {
        "speaker_email": "",
        "source": "unresolved",
        "confidence": 0.0,
        "quote_attribution_status": "unresolved",
        "quote_attribution_reason": (
            "Quoted ownership remains unresolved because the visible reply chain includes multiple plausible speakers."
        ),
        "candidate_emails": list(dict.fromkeys([*quoted_block_emails, *reply_context_identities])),
        "downgraded_due_to_quote_ambiguity": True,
    }


def _infer_quoted_speaker(
    *,
    full_email: dict[str, Any] | None,
    authored_email: str,
    conversation_context: dict[str, Any] | None,
    segment_text: str = "",
) -> tuple[str, str, float]:
    """Infer a likely quoted speaker and attribution provenance."""
    decision = _quote_attribution_details(
        full_email=full_email,
        authored_email=authored_email,
        conversation_context=conversation_context,
        segment_text=segment_text,
    )
    return (
        str(decision.get("speaker_email") or ""),
        str(decision.get("source") or "unresolved"),
        float(decision.get("confidence") or 0.0),
    )


def _speaker_attribution_for_candidate(
    db: Any,
    *,
    uid: str,
    conversation_id: str,
    sender_email: str,
    sender_name: str,
    conversation_context: dict[str, Any] | None,
    full_email: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Build authored vs quoted speaker hints for one candidate."""
    segments = _segment_rows_for_uid(db, uid)
    if not segments:
        return None
    quoted_blocks: list[dict[str, Any]] = []
    for segment in segments:
        segment_type = str(segment.get("segment_type") or "")
        if segment_type not in {"quoted_reply", "forwarded_message"}:
            continue
        quote_attribution = _quote_attribution_details(
            full_email=full_email,
            authored_email=sender_email,
            conversation_context=conversation_context,
            segment_text=str(segment.get("text") or ""),
        )
        quoted_blocks.append(
            {
                "segment_ordinal": int(segment.get("ordinal") or 0),
                "segment_type": segment_type,
                "speaker_email": str(quote_attribution.get("speaker_email") or ""),
                "source": str(quote_attribution.get("source") or ""),
                "confidence": float(quote_attribution.get("confidence") or 0.0),
                "quote_attribution_status": str(quote_attribution.get("quote_attribution_status") or ""),
                "quote_attribution_reason": str(quote_attribution.get("quote_attribution_reason") or ""),
                "candidate_emails": list(quote_attribution.get("candidate_emails") or []),
                "downgraded_due_to_quote_ambiguity": bool(
                    quote_attribution.get("downgraded_due_to_quote_ambiguity", True)
                ),
                "text": str(segment.get("text") or ""),
            }
        )
    authored_email = sender_email
    authored_name = sender_name
    if db and conversation_id and hasattr(db, "get_thread_emails"):
        thread_emails = db.get_thread_emails(conversation_id) or []
        for email in thread_emails:
            if str(email.get("uid") or "") != uid:
                continue
            authored_email = str(email.get("sender_email") or authored_email)
            authored_name = str(email.get("sender_name") or authored_name)
            break
    return {
        "authored_speaker": {
            "email": authored_email,
            "name": authored_name,
            "source": "canonical_sender",
            "confidence": 1.0,
        },
        "quoted_blocks": quoted_blocks,
    }


def _authored_text_for_candidate(
    db: Any,
    *,
    uid: str,
    full_email: dict[str, Any] | None,
    fallback_text: str,
) -> str:
    """Return best-effort authored-only text for one message."""
    segments = _segment_rows_for_uid(db, uid)
    if segments:
        authored_parts = [
            str(segment.get("text") or "")
            for segment in segments
            if str(segment.get("segment_type") or "") not in {"quoted_reply", "forwarded_message"}
            and str(segment.get("text") or "").strip()
        ]
        if authored_parts:
            return "\n".join(authored_parts)
    if full_email:
        for field in ("forensic_body_text", "body_text", "normalized_body_text"):
            text = str(full_email.get(field) or "").strip()
            if text:
                return text
    return fallback_text


def _language_rhetoric_for_candidate(
    db: Any,
    *,
    uid: str,
    full_email: dict[str, Any] | None,
    fallback_text: str,
    speaker_attribution: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return authored-vs-quoted language analysis for one case-scoped message."""
    authored_analysis = analyze_message_rhetoric(
        _authored_text_for_candidate(
            db,
            uid=uid,
            full_email=full_email,
            fallback_text=fallback_text,
        ),
        text_scope="authored_text",
    )
    quoted_block_analyses: list[dict[str, Any]] = []
    if isinstance(speaker_attribution, dict):
        for block in speaker_attribution.get("quoted_blocks", []):
            if not isinstance(block, dict):
                continue
            block_text = str(block.get("text") or "")
            analysis = analyze_message_rhetoric(block_text, text_scope="quoted_text")
            quoted_block_analyses.append(
                {
                    "segment_ordinal": int(block.get("segment_ordinal") or 0),
                    "segment_type": str(block.get("segment_type") or ""),
                    "speaker_email": str(block.get("speaker_email") or ""),
                    "speaker_source": str(block.get("source") or ""),
                    "speaker_confidence": float(block.get("confidence") or 0.0),
                    "quote_attribution_status": str(block.get("quote_attribution_status") or ""),
                    "quote_attribution_reason": str(block.get("quote_attribution_reason") or ""),
                    "candidate_emails": list(block.get("candidate_emails") or []),
                    "downgraded_due_to_quote_ambiguity": bool(
                        block.get("downgraded_due_to_quote_ambiguity", True)
                    ),
                    "text": block_text,
                    "analysis": analysis,
                }
            )
    quoted_signal_count = sum(int(block["analysis"]["signal_count"]) for block in quoted_block_analyses)
    return {
        "version": LANGUAGE_RHETORIC_VERSION,
        "authored_text": authored_analysis,
        "quoted_blocks": quoted_block_analyses,
        "summary": {
            "authored_signal_count": int(authored_analysis["signal_count"]),
            "quoted_signal_count": quoted_signal_count,
            "total_signal_count": int(authored_analysis["signal_count"]) + quoted_signal_count,
        },
    }


def _message_findings_for_candidate(
    *,
    db: Any,
    uid: str,
    full_email: dict[str, Any] | None,
    language_rhetoric: dict[str, Any],
    case_scope: Any,
) -> dict[str, Any]:
    """Return message-level behavioural findings derived from rhetoric plus message context."""
    visible_recipients = [
        str(value).strip().lower()
        for field in ("to", "cc", "bcc")
        for value in ((full_email or {}).get(field) or [])
        if value
    ]
    target_email = str(getattr(case_scope.target_person, "email", "") or "")
    target_name = str(getattr(case_scope.target_person, "name", "") or "")
    authored_analysis = analyze_message_behavior(
        _authored_text_for_candidate(
            db,
            uid=uid,
            full_email=full_email,
            fallback_text=str((full_email or {}).get("body_text") or ""),
        ),
        text_scope="authored_text",
        rhetoric=language_rhetoric["authored_text"],
        recipient_count=len(visible_recipients),
        visible_recipient_emails=visible_recipients,
        case_target_email=target_email,
        case_target_name=target_name,
    )
    quoted_block_findings: list[dict[str, Any]] = []
    for block in language_rhetoric.get("quoted_blocks", []):
        if not isinstance(block, dict):
            continue
        quoted_block_findings.append(
            {
                "segment_ordinal": int(block.get("segment_ordinal") or 0),
                "segment_type": str(block.get("segment_type") or ""),
                "speaker_email": str(block.get("speaker_email") or ""),
                "speaker_source": str(block.get("speaker_source") or ""),
                "speaker_confidence": float(block.get("speaker_confidence") or 0.0),
                "quote_attribution_status": str(block.get("quote_attribution_status") or ""),
                "quote_attribution_reason": str(block.get("quote_attribution_reason") or ""),
                "candidate_emails": list(block.get("candidate_emails") or []),
                "downgraded_due_to_quote_ambiguity": bool(block.get("downgraded_due_to_quote_ambiguity", True)),
                "findings": analyze_message_behavior(
                    str(block.get("text") or ""),
                    text_scope="quoted_text",
                    rhetoric=block.get("analysis", {}),
                ),
            }
        )
    quoted_candidate_count = sum(
        int(block["findings"]["behavior_candidate_count"]) for block in quoted_block_findings
    )
    return {
        "version": MESSAGE_BEHAVIOR_VERSION,
        "authored_text": authored_analysis,
        "quoted_blocks": quoted_block_findings,
        "summary": {
            "authored_behavior_candidate_count": int(authored_analysis["behavior_candidate_count"]),
            "quoted_behavior_candidate_count": quoted_candidate_count,
            "total_behavior_candidate_count": int(authored_analysis["behavior_candidate_count"]) + quoted_candidate_count,
            "wording_only_signal_count": len(authored_analysis["wording_only_signal_ids"])
            + sum(len(block["findings"]["wording_only_signal_ids"]) for block in quoted_block_findings),
        },
    }


def _apply_actor_ids_to_case_bundle(case_bundle: dict[str, Any], actor_graph: dict[str, Any]) -> None:
    """Annotate case-bundle parties with stable actor ids."""
    scope = case_bundle.get("scope")
    if not isinstance(scope, dict):
        return
    target_person = scope.get("target_person")
    if isinstance(target_person, dict):
        actor_id, resolution = resolve_actor_id(
            actor_graph,
            email=str(target_person.get("email") or ""),
            name=str(target_person.get("name") or ""),
        )
        target_person["actor_id"] = actor_id
        target_person["actor_resolution"] = resolution
    comparator_actors = scope.get("comparator_actors")
    if isinstance(comparator_actors, list):
        for actor in comparator_actors:
            if not isinstance(actor, dict):
                continue
            actor_id, resolution = resolve_actor_id(
                actor_graph,
                email=str(actor.get("email") or ""),
                name=str(actor.get("name") or ""),
            )
            actor["actor_id"] = actor_id
            actor["actor_resolution"] = resolution
    suspected_actors = scope.get("suspected_actors")
    if isinstance(suspected_actors, list):
        for actor in suspected_actors:
            if not isinstance(actor, dict):
                continue
            actor_id, resolution = resolve_actor_id(
                actor_graph,
                email=str(actor.get("email") or ""),
                name=str(actor.get("name") or ""),
            )
            actor["actor_id"] = actor_id
            actor["actor_resolution"] = resolution


def _apply_actor_ids_to_candidates(items: list[dict[str, Any]], actor_graph: dict[str, Any]) -> None:
    """Annotate candidates and speaker hints with stable actor ids."""
    for item in items:
        actor_id, resolution = resolve_actor_id(
            actor_graph,
            email=str(item.get("sender_email") or ""),
            name=str(item.get("sender_name") or ""),
        )
        item["sender_actor_id"] = actor_id
        item["sender_actor_resolution"] = resolution
        speaker_attribution = item.get("speaker_attribution")
        if not isinstance(speaker_attribution, dict):
            continue
        authored_speaker = speaker_attribution.get("authored_speaker")
        if isinstance(authored_speaker, dict):
            authored_actor_id, authored_resolution = resolve_actor_id(
                actor_graph,
                email=str(authored_speaker.get("email") or ""),
                name=str(authored_speaker.get("name") or ""),
            )
            authored_speaker["actor_id"] = authored_actor_id
            authored_speaker["actor_resolution"] = authored_resolution
        quoted_blocks = speaker_attribution.get("quoted_blocks")
        if isinstance(quoted_blocks, list):
            for block in quoted_blocks:
                if not isinstance(block, dict):
                    continue
                quoted_actor_id, quoted_resolution = resolve_actor_id(
                    actor_graph,
                    email=str(block.get("speaker_email") or ""),
                )
                block["actor_id"] = quoted_actor_id
                block["actor_resolution"] = quoted_resolution


def _quote_attribution_metrics(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Return case-scoped quote-attribution quality metrics for BA14 analysis."""
    from collections import Counter

    status_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    quote_finding_count = 0
    downgraded_quote_finding_count = 0
    for candidate in candidates:
        speaker_attribution = candidate.get("speaker_attribution")
        if isinstance(speaker_attribution, dict):
            for block in speaker_attribution.get("quoted_blocks", []) or []:
                if not isinstance(block, dict):
                    continue
                status_counts[str(block.get("quote_attribution_status") or "unresolved")] += 1
                source_counts[str(block.get("source") or "unresolved")] += 1
        message_findings = candidate.get("message_findings")
        if not isinstance(message_findings, dict):
            continue
        for block in message_findings.get("quoted_blocks", []) or []:
            if not isinstance(block, dict):
                continue
            findings = block.get("findings")
            if not isinstance(findings, dict):
                continue
            behavior_count = len(list(findings.get("behavior_candidates") or []))
            quote_finding_count += behavior_count
            if bool(block.get("downgraded_due_to_quote_ambiguity", True)):
                downgraded_quote_finding_count += behavior_count

    quoted_block_count = sum(status_counts.values())
    resolved_block_count = quoted_block_count - int(status_counts.get("unresolved", 0))
    return {
        "version": "1",
        "quoted_block_count": quoted_block_count,
        "resolved_block_count": resolved_block_count,
        "unresolved_block_count": int(status_counts.get("unresolved", 0)),
        "status_counts": dict(sorted(status_counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "quote_finding_count": quote_finding_count,
        "downgraded_quote_finding_count": downgraded_quote_finding_count,
        "summary": {
            "authored_text_and_quoted_history_separated": True,
            "inferred_quote_cues_separated": True,
        },
    }


def _thread_graph_for_email(
    full_email: dict[str, Any] | None,
    *,
    fallback_conversation_id: str = "",
) -> dict[str, Any] | None:
    """Return canonical vs inferred thread graph fields for one email."""
    if not full_email and not fallback_conversation_id:
        return None
    references = []
    if full_email:
        raw_references = full_email.get("references") or []
        if not raw_references and full_email.get("references_json"):
            try:
                raw_references = json.loads(str(full_email.get("references_json") or "[]"))
            except json.JSONDecodeError:
                raw_references = []
        if isinstance(raw_references, list):
            references = [str(reference) for reference in raw_references if reference]
    conversation_id = str((full_email or {}).get("conversation_id") or fallback_conversation_id or "")
    in_reply_to = str((full_email or {}).get("in_reply_to") or "")
    canonical = {
        "conversation_id": conversation_id,
        "in_reply_to": in_reply_to,
        "references": references,
        "has_thread_links": bool(conversation_id or in_reply_to or references),
    }
    inferred = {
        "parent_uid": str((full_email or {}).get("inferred_parent_uid") or ""),
        "thread_id": str((full_email or {}).get("inferred_thread_id") or ""),
        "reason": str((full_email or {}).get("inferred_match_reason") or ""),
        "confidence": float((full_email or {}).get("inferred_match_confidence") or 0.0),
    }
    inferred["has_parent_link"] = bool(inferred["parent_uid"] or inferred["thread_id"])
    return {
        "canonical": canonical,
        "inferred": inferred,
    }


def _thread_locator_for_candidate(
    candidate: dict[str, Any],
    full_email: dict[str, Any] | None,
) -> dict[str, str]:
    """Return the grouping locator for one candidate without conflating canonical and inferred ids."""
    canonical_conversation_id = str(candidate.get("conversation_id") or (full_email or {}).get("conversation_id") or "")
    inferred_thread_id = str((full_email or {}).get("inferred_thread_id") or "")
    if canonical_conversation_id:
        return {
            "conversation_id": canonical_conversation_id,
            "inferred_thread_id": inferred_thread_id,
            "thread_group_id": canonical_conversation_id,
            "thread_group_source": "canonical",
        }
    if inferred_thread_id:
        return {
            "conversation_id": "",
            "inferred_thread_id": inferred_thread_id,
            "thread_group_id": inferred_thread_id,
            "thread_group_source": "inferred",
        }
    return {
        "conversation_id": "",
        "inferred_thread_id": "",
        "thread_group_id": "",
        "thread_group_source": "",
    }


def _provenance_for_candidate(
    db: Any,
    uid: str,
    retrieval_snippet: str,
    *,
    metadata: dict[str, Any],
) -> tuple[str, str, str, str, dict[str, Any], dict[str, Any] | None]:
    """Resolve render provenance and a stable evidence handle for one candidate."""
    requested_mode = str(metadata.get("evidence_mode") or "retrieval")
    body_render_mode = "forensic" if requested_mode == "forensic" else "retrieval"
    body_render_source = str(metadata.get("body_render_source") or metadata.get("normalized_body_source") or "search_result_text")
    snippet = retrieval_snippet
    snippet_start: int | None = None
    snippet_end: int | None = None
    segment_ordinal: int | None = None
    verification_status = "retrieval"

    full_map = db.get_emails_full_batch([uid]) if db and uid and hasattr(db, "get_emails_full_batch") else {}
    full_email = full_map.get(uid) if isinstance(full_map, dict) else None
    if full_email:
        has_forensic_text = bool((full_email.get("forensic_body_text") or "").strip())
        if requested_mode == "forensic":
            body_text, body_render_source = resolve_body_for_render(full_email, "forensic" if has_forensic_text else "retrieval")
            body_render_mode = "forensic" if has_forensic_text else "retrieval"
            snippet, status_suffix, snippet_start, snippet_end = _verified_snippet_for_mode(body_text, retrieval_snippet)
            verification_status = (
                "forensic_exact" if status_suffix == "exact" and body_render_mode == "forensic" else "forensic_fallback_retrieval"
            )
        elif requested_mode == "hybrid":
            if has_forensic_text:
                forensic_text, forensic_source = resolve_body_for_render(full_email, "forensic")
                body_render_mode = "forensic"
                body_render_source = forensic_source
                snippet, status_suffix, snippet_start, snippet_end = _verified_snippet_for_mode(forensic_text, retrieval_snippet)
                verification_status = "hybrid_verified_forensic" if status_suffix == "exact" else "hybrid_forensic_fallback"
            else:
                body_text, body_render_source = resolve_body_for_render(full_email, "retrieval")
                snippet, _, snippet_start, snippet_end = _verified_snippet_for_mode(body_text, retrieval_snippet)
                verification_status = "hybrid_fallback_retrieval"
        else:
            body_text, body_render_source = resolve_body_for_render(full_email, "retrieval")
            snippet, _, snippet_start, snippet_end = _verified_snippet_for_mode(body_text, retrieval_snippet)
        segment_ordinal = _segment_ordinal_for_snippet(db, uid, snippet)

    if snippet_start is None:
        snippet_start = 0
        snippet_end = len(snippet)

    handle = f"email:{uid}:{body_render_mode}:{body_render_source}:{snippet_start}:{snippet_end}"
    if segment_ordinal is not None:
        handle += f":{segment_ordinal}"

    provenance = {
        "evidence_handle": handle,
        "uid": uid,
        "body_render_mode": body_render_mode,
        "body_render_source": body_render_source,
        "snippet_start": snippet_start,
        "snippet_end": snippet_end,
        "segment_ordinal": segment_ordinal,
    }
    return snippet, body_render_mode, body_render_source, verification_status, provenance, full_email


async def build_answer_context(deps: ToolDepsProto, params: EmailAnswerContextInput) -> str:
    """Build the answer-context payload for ``email_answer_context``."""

    def _run() -> str:
        from ..config import get_settings

        settings = get_settings()
        r = deps.get_retriever()
        db = deps.get_email_db()
        effective_top_k = min(params.max_results, settings.mcp_max_search_results)
        search_kwargs = _answer_context_search_kwargs(params, effective_top_k)
        results = r.search_filtered(**search_kwargs)
        candidates: list[dict[str, Any]] = []
        attachment_candidates: list[dict[str, Any]] = []
        for rank, result in enumerate(results, start=1):
            metadata = result.metadata
            uid = str(metadata.get("uid", ""))
            if _is_attachment_result(metadata, chunk_id=result.chunk_id):
                attachment_candidates.append(
                    _attachment_candidate(
                        db,
                        result,
                        rank=rank,
                        params=params,
                    )
                )
                continue
            retrieval_snippet = _snippet(result.text)
            metadata = {**metadata, "evidence_mode": params.evidence_mode}
            (
                snippet,
                body_render_mode,
                body_render_source,
                verification_status,
                provenance,
                _full_email,
            ) = _provenance_for_candidate(
                db,
                uid,
                retrieval_snippet,
                metadata=metadata,
            )
            candidate = {
                "rank": rank,
                "uid": uid,
                "subject": metadata.get("subject", ""),
                "sender_email": metadata.get("sender_email", ""),
                "sender_name": metadata.get("sender_name", ""),
                "date": metadata.get("date", ""),
                "conversation_id": metadata.get("conversation_id", ""),
                "score": result.score,
                "snippet": snippet,
                "match_reason": _match_reason(rank, params),
                "body_render_mode": body_render_mode,
                "body_render_source": body_render_source,
                "verification_status": verification_status,
                "provenance": provenance,
                "follow_up": {
                    "tool": "email_deep_context",
                    "uid": uid,
                },
            }
            candidates.append(candidate)

        candidates, deduped_body = _dedupe_evidence_items(candidates)
        attachment_candidates, deduped_attachments = _dedupe_evidence_items(attachment_candidates)
        _reindex_evidence(candidates)
        _reindex_evidence(attachment_candidates)

        candidate_uids = [
            str(candidate.get("uid") or "") for candidate in [*candidates, *attachment_candidates] if candidate.get("uid")
        ]
        full_map = db.get_emails_full_batch(candidate_uids) if db and hasattr(db, "get_emails_full_batch") else {}
        for candidate in [*candidates, *attachment_candidates]:
            full_email = full_map.get(str(candidate.get("uid") or "")) if isinstance(full_map, dict) else None
            candidate.update(_thread_locator_for_candidate(candidate, full_email))
            thread_graph = _thread_graph_for_email(
                full_email,
                fallback_conversation_id=str(candidate.get("conversation_id") or ""),
            )
            if thread_graph:
                candidate["thread_graph"] = thread_graph
        conversation_groups, conversation_group_by_id = _conversation_group_summaries(
            db,
            candidates=candidates,
            attachment_candidates=attachment_candidates,
        )
        _attach_conversation_context([*candidates, *attachment_candidates], conversation_group_by_id)
        for candidate in candidates:
            full_email = full_map.get(str(candidate.get("uid") or "")) if isinstance(full_map, dict) else None
            weak_message = weak_message_semantics(full_email or {})
            if weak_message:
                candidate["weak_message"] = weak_message
            speaker_attribution = _speaker_attribution_for_candidate(
                db,
                uid=str(candidate.get("uid") or ""),
                conversation_id=str(candidate.get("conversation_id") or ""),
                sender_email=str(candidate.get("sender_email") or ""),
                sender_name=str(candidate.get("sender_name") or ""),
                conversation_context=(
                    candidate.get("conversation_context") if isinstance(candidate.get("conversation_context"), dict) else None
                ),
                full_email=full_email,
            )
            if speaker_attribution:
                candidate["speaker_attribution"] = speaker_attribution
            if params.case_scope is not None:
                candidate["language_rhetoric"] = _language_rhetoric_for_candidate(
                    db,
                    uid=str(candidate.get("uid") or ""),
                    full_email=full_email,
                    fallback_text=str(candidate.get("snippet") or ""),
                    speaker_attribution=speaker_attribution,
                )
                candidate["message_findings"] = _message_findings_for_candidate(
                    db=db,
                    uid=str(candidate.get("uid") or ""),
                    full_email=full_email,
                    language_rhetoric=candidate["language_rhetoric"],
                    case_scope=params.case_scope,
                )

        def _rebuild_sections() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
            groups, by_id = _conversation_group_summaries(
                db,
                candidates=candidates,
                attachment_candidates=attachment_candidates,
            )
            _attach_conversation_context([*candidates, *attachment_candidates], by_id)
            answer_quality = _answer_quality(
                candidates=candidates,
                attachment_candidates=attachment_candidates,
                conversation_groups=groups,
            )
            return (
                groups,
                answer_quality,
                _timeline_summary(
                    candidates=candidates,
                    attachment_candidates=attachment_candidates,
                ),
                answer_policy := _answer_policy(
                    question=params.question,
                    evidence_mode=params.evidence_mode,
                    candidates=candidates,
                    attachment_candidates=attachment_candidates,
                    answer_quality=answer_quality,
                ),
                _final_answer_contract(answer_policy=answer_policy),
            )

        def _build_payload(
            groups: list[dict[str, Any]],
            answer_quality: dict[str, Any],
            timeline: dict[str, Any],
            answer_policy: dict[str, Any],
            final_answer_contract: dict[str, Any],
            final_answer: dict[str, Any],
            compact_policy_contract: bool = False,
            compact_search: bool = False,
            compact_case_evidence: bool = False,
            packing: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            def _public_item(item: dict[str, Any]) -> dict[str, Any]:
                public = dict(item)
                public.pop("thread_group_id", None)
                public.pop("thread_group_source", None)
                public.pop("inferred_thread_id", None)
                return public

            if compact_policy_contract:
                answer_policy_payload = {
                    "decision": str(answer_policy.get("decision") or ""),
                    "verification_mode": str(answer_policy.get("verification_mode") or ""),
                    "max_citations": int(answer_policy.get("max_citations") or 0),
                    "cite_candidate_uids": [str(uid) for uid in answer_policy.get("cite_candidate_uids", []) if uid],
                    "refuse_to_overclaim": bool(answer_policy.get("refuse_to_overclaim", True)),
                }
                final_answer_contract_payload = {
                    "decision": str(final_answer_contract.get("decision") or ""),
                    "answer_shape": str((final_answer_contract.get("answer_format") or {}).get("shape") or ""),
                    "citation_style": str((final_answer_contract.get("citation_format") or {}).get("style") or ""),
                    "required_citation_uids": [
                        str(uid) for uid in final_answer_contract.get("required_citation_uids", []) if uid
                    ],
                    "verification_mode": str(final_answer_contract.get("verification_mode") or ""),
                    "refuse_to_overclaim": bool(final_answer_contract.get("refuse_to_overclaim", True)),
                }
            else:
                answer_policy_payload = answer_policy
                final_answer_contract_payload = final_answer_contract

            search_payload: dict[str, Any]
            if compact_search:
                search_payload = {
                    "top_k": effective_top_k,
                }
            else:
                search_payload = {
                    "top_k": effective_top_k,
                    "sender": params.sender,
                    "subject": params.subject,
                    "folder": params.folder,
                    "has_attachments": params.has_attachments,
                    "email_type": params.email_type,
                    "date_from": params.date_from
                    if params.date_from is not None
                    else (params.case_scope.date_from if params.case_scope is not None else None),
                    "date_to": params.date_to
                    if params.date_to is not None
                    else (params.case_scope.date_to if params.case_scope is not None else None),
                    "rerank": params.rerank,
                    "hybrid": params.hybrid,
                }

            payload: dict[str, Any] = {
                "question": params.question,
                "count": len(candidates) + len(attachment_candidates),
                "counts": {
                    "body": len(candidates),
                    "attachments": len(attachment_candidates),
                    "total": len(candidates) + len(attachment_candidates),
                },
                "candidates": [_public_item(candidate) for candidate in candidates],
                "attachment_candidates": [_public_item(candidate) for candidate in attachment_candidates],
                "conversation_groups": groups,
                "answer_quality": answer_quality,
                "timeline": timeline,
                "answer_policy": answer_policy_payload,
                "final_answer_contract": final_answer_contract_payload,
                "final_answer": final_answer,
                "evidence_mode": {
                    "requested": params.evidence_mode,
                },
                "search": search_payload,
            }
            if case_bundle is not None:
                payload["case_bundle"] = case_bundle
            if case_bundle is not None:
                finding_evidence_payload = finding_evidence_index
                evidence_table_payload = evidence_table
                if compact_case_evidence:
                    finding_evidence_payload = {
                        "version": str(finding_evidence_index.get("version") or ""),
                        "finding_count": int(finding_evidence_index.get("finding_count") or 0),
                        "summary": {
                            "finding_ids": [
                                str(finding.get("finding_id") or "")
                                for finding in list(finding_evidence_index.get("findings") or [])[:3]
                                if isinstance(finding, dict)
                            ],
                        },
                    }
                    evidence_table_payload = {
                        "version": str(evidence_table.get("version") or ""),
                        "row_count": int(evidence_table.get("row_count") or 0),
                        "summary": dict(evidence_table.get("summary") or {}),
                    }
                    strength_rubric_payload = {
                        "version": str(behavioral_strength_rubric.get("version") or ""),
                        "labels": list(behavioral_strength_rubric.get("labels") or []),
                    }
                else:
                    strength_rubric_payload = behavioral_strength_rubric
                investigation_report_payload = investigation_report
                if compact_case_evidence and investigation_report is not None:
                    investigation_report_payload = compact_investigation_report(investigation_report)
                payload["actor_identity_graph"] = {
                    "actors": actor_graph.get("actors", []),
                    "unresolved_references": actor_graph.get("unresolved_references", []),
                    "stats": actor_graph.get("stats", {}),
                }
                payload["power_context"] = power_context
                payload["behavioral_taxonomy"] = behavioral_taxonomy_payload(
                    allegation_focus=list(params.case_scope.allegation_focus) if params.case_scope is not None else []
                )
                payload["case_patterns"] = case_patterns
                payload["retaliation_analysis"] = retaliation_analysis
                payload["comparative_treatment"] = comparative_treatment
                payload["communication_graph"] = communication_graph
                payload["multi_source_case_bundle"] = multi_source_case_bundle
                payload["finding_evidence_index"] = finding_evidence_payload
                payload["evidence_table"] = evidence_table_payload
                payload["behavioral_strength_rubric"] = strength_rubric_payload
                payload["quote_attribution_metrics"] = quote_attribution_metrics
                payload["investigation_report"] = investigation_report_payload
            if not candidates and not attachment_candidates:
                payload["message"] = "No candidate evidence found for the question."
            if effective_top_k < params.max_results:
                payload["_capped"] = {
                    "requested": params.max_results,
                    "effective": effective_top_k,
                    "profile": settings.mcp_model_profile,
                }
            if packing is not None:
                payload["_packed"] = packing
            return payload

        conversation_groups, answer_quality, timeline, answer_policy, final_answer_contract = _rebuild_sections()

        def _cited_candidate_uids() -> list[str]:
            return [str(uid) for uid in answer_policy.get("cite_candidate_uids", []) if uid]

        deduplicated: dict[str, int] = {
            "body_candidates": deduped_body,
            "attachment_candidates": deduped_attachments,
        }
        compact_policy_contract = False
        compact_search = False
        compact_case_evidence = False
        truncated: dict[str, int] = {
            "body_candidates": 0,
            "attachment_candidates": 0,
            "conversation_groups": 0,
            "timeline_events": 0,
            "snippet_compactions": 0,
            "field_compactions": 0,
        }
        packing: dict[str, Any] = {
            "applied": False,
            "budget_chars": settings.mcp_max_json_response_chars,
            "estimated_chars_before": 0,
            "estimated_chars_after": 0,
            "deduplicated": deduplicated,
            "truncated": truncated,
        }
        case_bundle = build_case_bundle(params.case_scope) if params.case_scope is not None else None
        actor_graph = resolve_actor_graph(
            case_scope=params.case_scope,
            candidates=candidates,
            attachment_candidates=attachment_candidates,
            full_map=full_map,
        )
        power_context = build_power_context(params.case_scope, actor_graph)
        apply_power_context_to_actor_graph(actor_graph, power_context)
        if case_bundle is not None:
            _apply_actor_ids_to_case_bundle(case_bundle, actor_graph)
        _apply_actor_ids_to_candidates(candidates, actor_graph)
        _apply_actor_ids_to_candidates(attachment_candidates, actor_graph)
        target_actor_id = ""
        if case_bundle is not None and isinstance(case_bundle.get("scope"), dict):
            target_actor_id = str(
                ((case_bundle["scope"].get("target_person") or {}) if isinstance(case_bundle["scope"], dict) else {}).get(
                    "actor_id"
                )
                or ""
            )
        case_patterns = (
            build_case_patterns(
                candidates=candidates,
                target_actor_id=target_actor_id,
            )
            if case_bundle is not None
            else None
        )
        retaliation_analysis = (
            build_retaliation_analysis(
                case_scope=params.case_scope,
                case_bundle=case_bundle,
                candidates=candidates,
            )
            if case_bundle is not None
            else None
        )
        comparative_treatment = (
            build_comparative_treatment(
                case_bundle=case_bundle,
                candidates=candidates,
                full_map=full_map if isinstance(full_map, dict) else {},
            )
            if case_bundle is not None
            else None
        )
        communication_graph = (
            build_communication_graph(
                case_bundle=case_bundle,
                candidates=candidates,
                full_map=full_map if isinstance(full_map, dict) else {},
            )
            if case_bundle is not None
            else None
        )
        multi_source_case_bundle = (
            build_multi_source_case_bundle(
                case_bundle=case_bundle,
                candidates=candidates,
                attachment_candidates=attachment_candidates,
                full_map=full_map if isinstance(full_map, dict) else {},
            )
            if case_bundle is not None
            else None
        )
        finding_evidence_index, evidence_table = (
            build_behavioral_evidence_chains(
                candidates=candidates,
                case_patterns=case_patterns,
                retaliation_analysis=retaliation_analysis,
                comparative_treatment=comparative_treatment,
                communication_graph=communication_graph,
            )
            if case_bundle is not None
            else ({}, {})
        )
        if case_bundle is not None:
            finding_evidence_index, evidence_table, behavioral_strength_rubric = apply_behavioral_strength(
                finding_evidence_index,
                evidence_table,
            )
        else:
            behavioral_strength_rubric = {}
        quote_attribution_metrics = _quote_attribution_metrics(candidates) if case_bundle is not None else {}
        investigation_report = (
            build_investigation_report(
                case_bundle=case_bundle,
                candidates=candidates,
                timeline=timeline,
                power_context=power_context,
                case_patterns=case_patterns,
                retaliation_analysis=retaliation_analysis,
                comparative_treatment=comparative_treatment,
                communication_graph=communication_graph,
                finding_evidence_index=finding_evidence_index,
                evidence_table=evidence_table,
            )
            if case_bundle is not None
            else None
        )
        initial_payload = _build_payload(
            conversation_groups,
            answer_quality,
            timeline,
            answer_policy,
            final_answer_contract,
            _render_final_answer(
                candidates=candidates,
                attachment_candidates=attachment_candidates,
                answer_policy=answer_policy,
                final_answer_contract=final_answer_contract,
            ),
            compact_policy_contract=compact_policy_contract,
            compact_search=compact_search,
        )
        packing["estimated_chars_before"] = _estimated_json_chars(initial_payload)
        packing["applied"] = bool(
            deduped_body or deduped_attachments or packing["estimated_chars_before"] > settings.mcp_max_json_response_chars > 0
        )

        def _current_payload() -> dict[str, Any]:
            return _build_payload(
                conversation_groups,
                answer_quality,
                timeline,
                answer_policy,
                final_answer_contract,
                _render_final_answer(
                    candidates=candidates,
                    attachment_candidates=attachment_candidates,
                    answer_policy=answer_policy,
                    final_answer_contract=final_answer_contract,
                ),
                compact_policy_contract=compact_policy_contract,
                compact_search=compact_search,
                compact_case_evidence=compact_case_evidence,
                packing=packing,
            )

        budget = settings.mcp_max_json_response_chars
        if budget > 0:
            if len(conversation_groups) > 3 and _estimated_json_chars(_current_payload()) > budget:
                truncated["conversation_groups"] = len(conversation_groups) - 3
                conversation_groups = conversation_groups[:3]
                answer_quality = _answer_quality(
                    candidates=candidates,
                    attachment_candidates=attachment_candidates,
                    conversation_groups=conversation_groups,
                )
                answer_policy = _answer_policy(
                    question=params.question,
                    evidence_mode=params.evidence_mode,
                    candidates=candidates,
                    attachment_candidates=attachment_candidates,
                    answer_quality=answer_quality,
                )
                final_answer_contract = _final_answer_contract(answer_policy=answer_policy)
                packing["applied"] = True
            compacted_timeline, dropped_events = _compact_timeline_events(timeline)
            if dropped_events > 0 and _estimated_json_chars(_current_payload()) > budget:
                timeline = compacted_timeline
                truncated["timeline_events"] = dropped_events
                packing["applied"] = True
            if _estimated_json_chars(_current_payload()) > budget:
                truncated["snippet_compactions"] += _compact_snippets_for_budget(
                    candidates,
                    attachment_candidates,
                    cited_candidate_uids=_cited_candidate_uids(),
                    phase="primary",
                )
                if truncated["snippet_compactions"] > 0:
                    conversation_groups, answer_quality, timeline, answer_policy, final_answer_contract = _rebuild_sections()
                    compacted_timeline, dropped_events = _compact_timeline_events(timeline)
                    if dropped_events > truncated["timeline_events"]:
                        truncated["timeline_events"] = dropped_events
                        timeline = compacted_timeline
                    packing["applied"] = True
            while _estimated_json_chars(_current_payload()) > budget and (len(candidates) + len(attachment_candidates)) > 1:
                weakest_target = _weakest_evidence_target(
                    candidates,
                    attachment_candidates,
                    cited_candidate_uids=_cited_candidate_uids(),
                )
                if weakest_target is None:
                    break
                kind, index = weakest_target
                if kind == "attachment":
                    attachment_candidates.pop(index)
                    truncated["attachment_candidates"] += 1
                else:
                    candidates.pop(index)
                    truncated["body_candidates"] += 1
                _reindex_evidence(candidates)
                _reindex_evidence(attachment_candidates)
                conversation_groups, answer_quality, timeline, answer_policy, final_answer_contract = _rebuild_sections()
                compacted_timeline, dropped_events = _compact_timeline_events(timeline)
                if dropped_events > truncated["timeline_events"]:
                    truncated["timeline_events"] = dropped_events
                    timeline = compacted_timeline
                packing["applied"] = True
            if _estimated_json_chars(_current_payload()) > budget:
                field_compactions = _strip_optional_evidence_fields(candidates, attachment_candidates)
                if field_compactions > 0:
                    truncated["field_compactions"] = field_compactions
                    conversation_groups, answer_quality, timeline, answer_policy, final_answer_contract = _rebuild_sections()
                    if conversation_groups:
                        summarized_groups, dropped_groups = _summarize_conversation_groups_for_budget(conversation_groups)
                        truncated["conversation_groups"] = max(truncated["conversation_groups"], dropped_groups)
                        conversation_groups = summarized_groups
                    if timeline.get("events"):
                        summarized_timeline, dropped_events = _summarize_timeline_for_budget(timeline)
                        truncated["timeline_events"] = max(truncated["timeline_events"], dropped_events)
                        timeline = summarized_timeline
                    answer_quality = _answer_quality(
                        candidates=candidates,
                        attachment_candidates=attachment_candidates,
                        conversation_groups=conversation_groups,
                    )
                    answer_policy = _answer_policy(
                        question=params.question,
                        evidence_mode=params.evidence_mode,
                        candidates=candidates,
                        attachment_candidates=attachment_candidates,
                        answer_quality=answer_quality,
                    )
                    final_answer_contract = _final_answer_contract(answer_policy=answer_policy)
                    packing["applied"] = True
            if _estimated_json_chars(_current_payload()) > budget:
                extra_compactions = _compact_snippets_for_budget(
                    candidates,
                    attachment_candidates,
                    cited_candidate_uids=_cited_candidate_uids(),
                    phase="secondary",
                )
                if extra_compactions > 0:
                    truncated["snippet_compactions"] += extra_compactions
                    conversation_groups, answer_quality, timeline, answer_policy, final_answer_contract = _rebuild_sections()
                    if conversation_groups:
                        summarized_groups, dropped_groups = _summarize_conversation_groups_for_budget(conversation_groups)
                        truncated["conversation_groups"] = max(truncated["conversation_groups"], dropped_groups)
                        conversation_groups = summarized_groups
                    if timeline.get("events"):
                        summarized_timeline, dropped_events = _summarize_timeline_for_budget(timeline)
                        truncated["timeline_events"] = max(truncated["timeline_events"], dropped_events)
                        timeline = summarized_timeline
                    answer_quality = _answer_quality(
                        candidates=candidates,
                        attachment_candidates=attachment_candidates,
                        conversation_groups=conversation_groups,
                    )
                    answer_policy = _answer_policy(
                        question=params.question,
                        evidence_mode=params.evidence_mode,
                        candidates=candidates,
                        attachment_candidates=attachment_candidates,
                        answer_quality=answer_quality,
                    )
                    final_answer_contract = _final_answer_contract(answer_policy=answer_policy)
                    packing["applied"] = True
            if _estimated_json_chars(_current_payload()) > budget and not compact_policy_contract:
                compact_policy_contract = True
                truncated["field_compactions"] += 2
                packing["applied"] = True
            if _estimated_json_chars(_current_payload()) > budget and not compact_search:
                compact_search = True
                truncated["field_compactions"] += 1
                packing["applied"] = True
            if _estimated_json_chars(_current_payload()) > budget and not compact_case_evidence and case_bundle is not None:
                compact_case_evidence = True
                truncated["field_compactions"] += 2
                packing["applied"] = True

        final_payload = _build_payload(
            conversation_groups,
            answer_quality,
            timeline,
            answer_policy,
            final_answer_contract,
            _render_final_answer(
                candidates=candidates,
                attachment_candidates=attachment_candidates,
                answer_policy=answer_policy,
                final_answer_contract=final_answer_contract,
            ),
            compact_policy_contract=compact_policy_contract,
            compact_search=compact_search,
            compact_case_evidence=compact_case_evidence,
        )
        packing["estimated_chars_after"] = _estimated_json_chars(final_payload)
        final_payload["_packed"] = packing
        return json_response(final_payload)

    return await deps.offload(_run)
