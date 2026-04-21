"""Answer quality, timeline, and final rendering helpers for answer context."""

from __future__ import annotations

import re
from typing import Any


def _is_weak_evidence_item(item: dict[str, Any]) -> bool:
    """Return whether one evidence item is weak for answer synthesis."""
    if item.get("weak_message"):
        return True
    attachment = item.get("attachment")
    return isinstance(attachment, dict) and attachment.get("evidence_strength") == "weak_reference"


def _evidence_rank_key(item: dict[str, Any]) -> tuple[float, float, str]:
    effective_score = _evidence_rank_score(item)
    reference = _citation_reference(item)
    reference_token = str(reference.get("evidence_handle") or reference.get("uid") or "")
    return (effective_score, float(item.get("score") or 0.0), reference_token)


def _evidence_rank_score(item: dict[str, Any]) -> float:
    score = float(item.get("score") or 0.0)
    score_calibration = str(item.get("score_calibration") or "").strip()
    score_kind = str(item.get("score_kind") or "").strip()
    verification_status = str(item.get("verification_status") or "").strip()
    attachment = item.get("attachment")
    if score_calibration == "calibrated":
        score += 0.03
    elif score_calibration == "synthetic":
        score -= 0.02
    if score_kind == "segment_sql":
        score += 0.015
    if isinstance(attachment, dict):
        score += 0.01
    if verification_status in {"retrieval_exact", "forensic_exact", "hybrid_verified_forensic", "segment_exact"}:
        score += 0.015
    if bool(item.get("exact_wording_requested")):
        body_render_source = str(item.get("body_render_source") or "").strip()
        if verification_status in {"forensic_exact", "segment_exact"}:
            score += 0.07
        elif verification_status in {"retrieval_exact", "hybrid_verified_forensic"}:
            score += 0.04
        if body_render_source in {"forensic_body_text", "message_segments", "quoted_reply"}:
            score += 0.02
        if verification_status in {"thread_context", "attachment_reference", "mixed_source_reference"}:
            score -= 0.025
    return score


def _answer_quality(
    *,
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
    conversation_groups: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a compact confidence and ambiguity summary for the answer bundle."""
    ordered = sorted([*candidates, *attachment_candidates], key=_evidence_rank_key, reverse=True)
    if not ordered:
        return {
            "confidence_label": "low",
            "confidence_score": 0.0,
            "ambiguity_reason": "no_evidence",
            "alternative_candidates": [],
            "alternative_candidate_references": [],
            "top_candidate_uid": "",
            "top_candidate_reference": {"uid": "", "evidence_handle": ""},
            "top_conversation_id": "",
            "top_thread_group_id": "",
            "top_thread_group_source": "",
        }

    top = ordered[0]
    top_score = _evidence_rank_score(top)
    second_score = _evidence_rank_score(ordered[1]) if len(ordered) > 1 else 0.0
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

    top_reference = _citation_reference(top)
    alternative_candidates = [str(item.get("uid") or "") for item in ordered[1:3] if item.get("uid")]
    alternative_candidate_references = [_citation_reference(item) for item in ordered[1:3]]
    if confidence_label == "high":
        alternative_candidates = []
        alternative_candidate_references = []

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
        "alternative_candidate_references": alternative_candidate_references,
        "top_candidate_uid": str(top.get("uid") or ""),
        "top_candidate_reference": top_reference,
        "top_conversation_id": top_conversation_id,
        "top_thread_group_id": top_thread_group_id,
        "top_thread_group_source": top_thread_group_source,
    }


_EXACT_WORDING_PATTERNS = (
    re.compile(r"\bexact(?:ly)?\b.*\b(?:quote|word(?:ing)?|words?)\b", re.IGNORECASE),
    re.compile(r"\b(?:exact quote|verbatim|word[- ]for[- ]word|literally)\b", re.IGNORECASE),
    re.compile(r"\bwhat(?:\s+exactly)?\s+did\b", re.IGNORECASE),
    re.compile(r"\b(?:g(?:enaue|enauen?) formulierung|g(?:enaue|enauen?) wortlaut)\b", re.IGNORECASE),
    re.compile(r"\b(?:mit welchem wortlaut|wie genau|wie lautete)\b", re.IGNORECASE),
    re.compile(r"\b(?:wörtlich|woertlich|wortlaut)\b", re.IGNORECASE),
)


def _question_requests_exact_wording(question: str) -> bool:
    """Return whether the question likely needs exact wording verification."""
    normalized = " ".join(str(question or "").split())
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in _EXACT_WORDING_PATTERNS)


def _resolve_exact_wording_requested(*, question: str, explicit: bool | None = None) -> bool:
    """Return quote intent from the propagated flag or question text."""
    if explicit is not None:
        return bool(explicit)
    return _question_requests_exact_wording(question)


def _citation_reference(item: dict[str, Any]) -> dict[str, str]:
    """Return the stable outward citation reference for one evidence item."""
    provenance = item.get("provenance")
    evidence_handle = str(item.get("evidence_handle") or "").strip()
    if isinstance(provenance, dict):
        evidence_handle = evidence_handle or str(provenance.get("evidence_handle") or "").strip()
    uid = str(item.get("uid") or "").strip()
    return {
        "uid": uid,
        "evidence_handle": evidence_handle,
    }


def _reference_token(reference: dict[str, str]) -> str:
    return str(reference.get("evidence_handle") or reference.get("uid") or "").strip()


def _citation_reference_payloads(value: Any) -> list[dict[str, str]]:
    """Return a normalized outward list of citation references."""
    if not isinstance(value, list):
        return []
    payloads: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        uid = str(item.get("uid") or "").strip()
        evidence_handle = str(item.get("evidence_handle") or "").strip()
        if not uid and not evidence_handle:
            continue
        payloads.append({"uid": uid, "evidence_handle": evidence_handle})
    return payloads


def _citation_token(reference: dict[str, str]) -> str:
    """Return one inline citation token."""
    evidence_handle = str(reference.get("evidence_handle") or "").strip()
    if evidence_handle:
        return f"[ref:{evidence_handle}]"
    uid = str(reference.get("uid") or "").strip()
    return f"[uid:{uid}]"


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
    exact_wording_requested: bool | None = None,
) -> dict[str, Any]:
    """Return deterministic answer-synthesis guidance for downstream callers."""
    confidence_label = str(answer_quality.get("confidence_label") or "low")
    ambiguity_reason = str(answer_quality.get("ambiguity_reason") or "")
    top_candidate_uid = str(answer_quality.get("top_candidate_uid") or "")
    alternative_candidates = [str(uid) for uid in answer_quality.get("alternative_candidates", []) if uid]
    top_candidate_reference = _citation_reference(answer_quality.get("top_candidate_reference") or {})
    alternative_candidate_references = _citation_reference_payloads(answer_quality.get("alternative_candidate_references"))
    exact_wording = _resolve_exact_wording_requested(question=question, explicit=exact_wording_requested)
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

    ordered = _ordered_evidence(candidates, attachment_candidates)
    cite_candidate_uids = [uid for uid in [top_candidate_uid, *alternative_candidates] if uid]
    requested_references = [top_candidate_reference, *alternative_candidate_references]
    requested_tokens = {_reference_token(reference) for reference in requested_references if _reference_token(reference)}
    citation_references: list[dict[str, str]] = []
    seen_tokens: set[str] = set()
    for item in ordered:
        reference = _citation_reference(item)
        token = _reference_token(reference)
        uid = str(item.get("uid") or "")
        if not token:
            continue
        if requested_tokens:
            if token not in requested_tokens:
                continue
        elif not uid or uid not in cite_candidate_uids:
            continue
        if token in seen_tokens:
            continue
        citation_references.append(reference)
        seen_tokens.add(token)
    max_citations = 1
    if decision == "ambiguous":
        requested_count = len([reference for reference in requested_references if _reference_token(reference)])
        max_citations = min(2, max(requested_count, len(cite_candidate_uids), 1))
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
        "exact_wording_requested": exact_wording,
        "max_citations": max_citations,
        "cite_candidate_uids": cite_candidate_uids[:max_citations],
        "cite_candidate_references": citation_references[:max_citations],
        "top_candidate_reference": top_candidate_reference,
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
    citation_references = _citation_reference_payloads(answer_policy.get("cite_candidate_references"))
    required_handles = [str(ref.get("evidence_handle") or "") for ref in citation_references if ref.get("evidence_handle")]
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
            "style": "inline_reference_brackets",
            "pattern": "[ref:<EVIDENCE_HANDLE>] or [uid:<EMAIL_UID>] when no evidence handle is available",
            "required_attribution": "Only cite references from required_citation_handles or required_citation_uids.",
        },
        "confidence_wording": str(answer_policy.get("confidence_phrase") or ""),
        "ambiguity_wording": str(answer_policy.get("ambiguity_phrase") or ""),
        "fallback_wording": str(answer_policy.get("fallback_phrase") or ""),
        "required_citation_uids": cite_candidate_uids,
        "required_citation_handles": required_handles,
        "required_citation_references": citation_references,
        "verification_mode": str(answer_policy.get("verification_mode") or ""),
        "exact_wording_requested": bool(answer_policy.get("exact_wording_requested")),
        "refuse_to_overclaim": bool(answer_policy.get("refuse_to_overclaim", True)),
    }


def _ordered_evidence(
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return answer evidence ordered by score descending."""
    return sorted([*candidates, *attachment_candidates], key=_evidence_rank_key, reverse=True)


def _evidence_description(item: dict[str, Any]) -> str:
    """Return a short human-readable description of one evidence item."""
    subject = str(item.get("subject") or "").strip()
    date = str(item.get("date") or "").strip()
    source_type = str(item.get("source_type") or "").strip()
    attachment = item.get("attachment")
    if source_type == "chat_log":
        base = f'the chat record "{subject or item.get("source_id") or "chat record"}"'
        if date:
            base += f" from {date[:10]}"
        return base
    if source_type in {"formal_document", "note_record", "time_record", "participation_record", "meeting_note"}:
        base = f'the {source_type.replace("_", " ")} "{subject or item.get("source_id") or "record"}"'
        if date:
            base += f" from {date[:10]}"
        return base
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


def _exact_excerpt(item: dict[str, Any]) -> str:
    snippet = " ".join(str(item.get("snippet") or "").split()).strip()
    if not snippet:
        return ""
    if len(snippet) > 240:
        snippet = snippet[:237].rstrip() + "..."
    return f'"{snippet}"'


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
    citation_references = _citation_reference_payloads(final_answer_contract.get("required_citation_references"))
    required_citation_uids = [str(uid) for uid in final_answer_contract.get("required_citation_uids", []) if uid]
    required_citation_handles = [str(handle) for handle in final_answer_contract.get("required_citation_handles", []) if handle]
    if not citation_references:
        citation_references = [
            {"uid": uid, "evidence_handle": required_citation_handles[index] if index < len(required_citation_handles) else ""}
            for index, uid in enumerate(required_citation_uids)
        ]
    if not citation_references:
        citation_references = [{"uid": uid, "evidence_handle": ""} for uid in required_citation_uids]
    citations = [_citation_token(reference) for reference in citation_references]
    citation_text = " ".join(citations)
    top_item = ordered[0] if ordered else None
    exact_wording_requested = bool(
        final_answer_contract.get("exact_wording_requested") or answer_policy.get("exact_wording_requested")
    )

    if decision == "ambiguous":
        citation_tokens = {_reference_token(reference) for reference in citation_references if _reference_token(reference)}
        cited_items = [item for item in ordered if _reference_token(_citation_reference(item)) in citation_tokens][:2]
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
            prefix = confidence or "The available evidence suggests"
            exact_excerpt = _exact_excerpt(top_item)
            verification_status = str(top_item.get("verification_status") or "")
            if (
                exact_wording_requested
                and exact_excerpt
                and verification_status
                in {
                    "retrieval_exact",
                    "forensic_exact",
                    "hybrid_verified_forensic",
                    "segment_exact",
                }
            ):
                sentence = f"{prefix} the exact wording is {exact_excerpt}."
            else:
                description = _evidence_description(top_item)
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
        "citations": [str(reference.get("evidence_handle") or reference.get("uid") or "") for reference in citation_references],
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
    sender_change_count = 0
    thread_change_count = 0
    recipient_set_change_count = 0
    previous_sender = ""
    previous_thread = ""
    previous_recipient_set = ""
    for index, item in enumerate(ordered, start=1):
        raw_recipients_summary = item.get("recipients_summary")
        recipients_summary: dict[str, Any] = raw_recipients_summary if isinstance(raw_recipients_summary, dict) else {}
        current_sender = str(item.get("sender_actor_id") or item.get("sender_email") or "")
        current_thread = str(item.get("thread_group_id") or item.get("conversation_id") or "")
        current_recipient_set = str(recipients_summary.get("signature") or "")
        sender_changed = bool(index > 1 and current_sender and previous_sender and current_sender != previous_sender)
        thread_changed = bool(index > 1 and current_thread and previous_thread and current_thread != previous_thread)
        recipient_set_changed = bool(
            index > 1 and current_recipient_set and previous_recipient_set and current_recipient_set != previous_recipient_set
        )
        if sender_changed:
            sender_change_count += 1
        if thread_changed:
            thread_change_count += 1
        if recipient_set_changed:
            recipient_set_change_count += 1
        events.append(
            {
                "sequence_index": index,
                "uid": str(item.get("uid") or ""),
                "date": str(item.get("date") or ""),
                "conversation_id": str(item.get("conversation_id") or ""),
                "thread_group_id": str(item.get("thread_group_id") or ""),
                "thread_group_source": str(item.get("thread_group_source") or ""),
                "sender_email": str(item.get("sender_email") or ""),
                "sender_name": str(item.get("sender_name") or ""),
                "sender_actor_id": str(item.get("sender_actor_id") or ""),
                "score": round(float(item.get("score") or 0.0), 3),
                "snippet": str(item.get("snippet") or ""),
                "recipients_summary": recipients_summary,
                "sender_changed_from_previous": sender_changed,
                "thread_changed_from_previous": thread_changed,
                "recipient_set_changed_from_previous": recipient_set_changed,
            }
        )
        previous_sender = current_sender or previous_sender
        previous_thread = current_thread or previous_thread
        previous_recipient_set = current_recipient_set or previous_recipient_set
    if not events:
        return {
            "event_count": 0,
            "date_range": {},
            "first_uid": "",
            "last_uid": "",
            "key_transition_uid": "",
            "unique_sender_count": 0,
            "unique_thread_group_count": 0,
            "sender_change_count": 0,
            "thread_change_count": 0,
            "recipient_set_change_count": 0,
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
        "unique_sender_count": len(
            {
                str(event.get("sender_actor_id") or event.get("sender_email") or "")
                for event in events
                if str(event.get("sender_actor_id") or event.get("sender_email") or "")
            }
        ),
        "unique_thread_group_count": len(
            {
                str(event.get("thread_group_id") or event.get("conversation_id") or "")
                for event in events
                if str(event.get("thread_group_id") or event.get("conversation_id") or "")
            }
        ),
        "sender_change_count": sender_change_count,
        "thread_change_count": thread_change_count,
        "recipient_set_change_count": recipient_set_change_count,
        "events": events,
    }
