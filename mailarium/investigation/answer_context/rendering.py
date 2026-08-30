"""Answer quality, timeline, and final rendering helpers for answer context."""

from __future__ import annotations

import re
from typing import Any

from mailarium.model.data_shapes import as_dict


def _is_weak_evidence_item(item: dict[str, Any]) -> bool:
    """Classify evidence as too weak to support a synthesized mailbox answer."""
    if item.get("weak_message"):
        return True
    attachment = item.get("attachment")
    return isinstance(attachment, dict) and attachment.get("evidence_strength") == "weak_reference"


def _evidence_rank_key(item: dict[str, Any]) -> tuple[float, float, str]:
    """Generate a sorting key for evidence items based on multiple score dimensions.

    Creates a composite key for sorting evidence items by effective score,
    raw score, and reference token to ensure deterministic ordering.

    Args:
        item: The evidence item dictionary.

    Returns:
        A tuple of (effective_score, raw_score, reference_token) for sorting.
    """
    effective_score = _evidence_rank_score(item)
    reference = _citation_reference(item)
    reference_token = str(reference.get("evidence_handle") or reference.get("uid") or "")
    return (effective_score, float(item.get("score") or 0.0), reference_token)


def _evidence_rank_score(item: dict[str, Any]) -> float:
    """Calculate the effective ranking score for an evidence item.

    Computes a calibrated score that incorporates base score, calibration type,
    score kind, verification status, attachment presence, and exact wording
    bonuses/penalties.

    Args:
        item: The evidence item dictionary.

    Returns:
        The adjusted score as a float.
    """
    return float(item.get("score") or 0.0) + _evidence_rank_adjustment(item)


def _evidence_rank_adjustment(item: dict[str, Any]) -> float:
    """Combine baseline calibration bonuses with exact-wording verification adjustments."""
    verification_status = str(item.get("verification_status") or "").strip()
    adjustment = _baseline_rank_adjustment(item, verification_status)
    return adjustment + _exact_wording_rank_adjustment(item, verification_status)


def _baseline_rank_adjustment(item: dict[str, Any], verification_status: str) -> float:
    """Sum calibration, segment-source, attachment, and verified-source ranking bonuses."""
    calibration_adjustment = {"calibrated": 0.03, "synthetic": -0.02}.get(str(item.get("score_calibration") or "").strip(), 0.0)
    score_kind_adjustment = 0.015 if str(item.get("score_kind") or "").strip() == "segment_sql" else 0.0
    attachment_adjustment = 0.01 if isinstance(item.get("attachment"), dict) else 0.0
    verified_adjustment = 0.015 if verification_status in _EXACT_VERIFICATION_STATUSES else 0.0
    return calibration_adjustment + score_kind_adjustment + attachment_adjustment + verified_adjustment


_EXACT_VERIFICATION_STATUSES = {"retrieval_exact", "forensic_exact", "hybrid_verified_forensic", "segment_exact"}


def _exact_wording_rank_adjustment(item: dict[str, Any], verification_status: str) -> float:
    """Reward exact verification and forensic source surfaces only for wording-sensitive questions."""
    if not bool(item.get("exact_wording_requested")):
        return 0.0
    verification_adjustment = {
        "forensic_exact": 0.07,
        "segment_exact": 0.07,
        "retrieval_exact": 0.04,
        "hybrid_verified_forensic": 0.04,
    }.get(verification_status, 0.0)
    source_adjustment = (
        0.02
        if str(item.get("body_render_source") or "").strip() in {"forensic_body_text", "message_segments", "quoted_reply"}
        else 0.0
    )
    weak_source_adjustment = (
        -0.025 if verification_status in {"thread_context", "attachment_reference", "mixed_source_reference"} else 0.0
    )
    return verification_adjustment + source_adjustment + weak_source_adjustment


def _answer_quality(
    *,
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
    conversation_groups: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a compact confidence and ambiguity summary for the answer bundle."""
    ordered = sorted([*candidates, *attachment_candidates], key=_evidence_rank_key, reverse=True)
    if not ordered:
        return _empty_answer_quality()

    top = ordered[0]
    top_score = _evidence_rank_score(top)
    second_score = _evidence_rank_score(ordered[1]) if len(ordered) > 1 else 0.0
    gap = top_score - second_score
    confidence_label, ambiguity_reason = _confidence_label(len(ordered), top_score, gap)
    alternatives, alternative_references = _alternative_candidates(ordered, confidence_label)
    thread_context = _top_thread_context(top, conversation_groups)

    return {
        "confidence_label": confidence_label,
        "confidence_score": round(top_score, 3),
        "ambiguity_reason": ambiguity_reason,
        "alternative_candidates": alternatives,
        "alternative_candidate_references": alternative_references,
        "top_candidate_uid": str(top.get("uid") or ""),
        "top_candidate_reference": _citation_reference(top),
        **thread_context,
    }


def _empty_answer_quality() -> dict[str, Any]:
    """Return the explicit low-confidence quality contract used when no evidence exists."""
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


def _confidence_label(item_count: int, top_score: float, gap: float) -> tuple[str, str]:
    """Classify confidence from top score and runner-up gap, flagging close scores as ambiguous."""
    if item_count > 1 and gap <= 0.03:
        return "ambiguous", "close_top_scores"
    if top_score >= 0.85 and gap >= 0.15:
        return "high", ""
    if top_score < 0.6:
        return "low", "weak_top_score"
    return "medium", ""


def _alternative_candidates(ordered: list[dict[str, Any]], confidence_label: str) -> tuple[list[str], list[dict[str, str]]]:
    """Expose at most two runner-up references unless the top candidate is high confidence."""
    if confidence_label == "high":
        return [], []
    alternatives = ordered[1:3]
    return [str(item.get("uid") or "") for item in alternatives if item.get("uid")], [
        _citation_reference(item) for item in alternatives
    ]


def _top_thread_context(top: dict[str, Any], conversation_groups: list[dict[str, Any]]) -> dict[str, str]:
    """Derive canonical or inferred thread identity from the leading conversation group or candidate."""
    if conversation_groups:
        group = conversation_groups[0]
        return {
            "top_conversation_id": str(group.get("conversation_id") or ""),
            "top_thread_group_id": str(group.get("thread_group_id") or ""),
            "top_thread_group_source": str(group.get("thread_group_source") or ""),
        }
    if top.get("conversation_id"):
        conversation_id = str(top.get("conversation_id") or "")
        return {
            "top_conversation_id": conversation_id,
            "top_thread_group_id": conversation_id,
            "top_thread_group_source": "canonical",
        }
    return {
        "top_conversation_id": "",
        "top_thread_group_id": str(top.get("inferred_thread_id") or ""),
        "top_thread_group_source": "inferred" if top.get("inferred_thread_id") else "",
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
    """Detect wording-sensitive questions that require an exact-source verification path."""
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
    """Extract a stable token from a citation reference for deduplication.

    Creates a string token from either evidence_handle or uid for use in
    tracking and deduplicating citations.

    Args:
        reference: A citation reference dictionary with uid and/or evidence_handle.

    Returns:
        The evidence_handle if present, otherwise the uid, or empty string.
    """
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
    """Detect when weak-message evidence dominates and must constrain the answer claim."""
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
    verification_mode = _verification_mode(evidence_mode, exact_wording, confidence_label, weak_evidence)
    decision = _answer_decision(confidence_label, ambiguity_reason, weak_evidence)
    cite_candidate_uids = [uid for uid in [top_candidate_uid, *alternative_candidates] if uid]
    requested_references = [top_candidate_reference, *alternative_candidate_references]
    citation_references = _requested_citation_references(
        candidates, attachment_candidates, requested_references, cite_candidate_uids
    )
    max_citations = _max_citations(decision, requested_references, cite_candidate_uids)

    return {
        "decision": decision,
        "verification_mode": verification_mode,
        "exact_wording_requested": exact_wording,
        "max_citations": max_citations,
        "cite_candidate_uids": cite_candidate_uids[:max_citations],
        "cite_candidate_references": citation_references[:max_citations],
        "top_candidate_reference": top_candidate_reference,
        "confidence_phrase": _confidence_phrase(decision, confidence_label),
        "ambiguity_phrase": "The available evidence is ambiguous",
        "fallback_phrase": (
            "I can identify the likely message, but the available evidence is too weak to state the content confidently."
        ),
        "refuse_to_overclaim": True,
    }


def _verification_mode(evidence_mode: str, exact_wording: bool, confidence_label: str, weak_evidence: bool) -> str:
    """Require forensic verification for exact, ambiguous, medium-confidence, or weak evidence cases."""
    needs_forensic = exact_wording or confidence_label in {"ambiguous", "medium"} or weak_evidence
    return (
        "verify_forensic"
        if evidence_mode != "forensic" and needs_forensic
        else "already_forensic"
        if evidence_mode == "forensic"
        else "retrieval_ok"
    )


def _answer_decision(confidence_label: str, ambiguity_reason: str, weak_evidence: bool) -> str:
    """Map confidence and weak-evidence reasons to answer, ambiguous, or insufficient-evidence states."""
    if confidence_label == "ambiguous":
        return "ambiguous"
    if confidence_label == "low" or ambiguity_reason in {"no_evidence", "weak_top_score", "weak_scan_body"} or weak_evidence:
        return "insufficient_evidence"
    return "answer"


def _requested_citation_references(
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
    requested_references: list[dict[str, str]],
    cite_uids: list[str],
) -> list[dict[str, str]]:
    """Select ordered evidence references that match requested handles or UIDs without duplicates."""
    requested_tokens = {_reference_token(reference) for reference in requested_references if _reference_token(reference)}
    references: list[dict[str, str]] = []
    for item in _ordered_evidence(candidates, attachment_candidates):
        reference = _citation_reference(item)
        token = _reference_token(reference)
        if (
            token
            and _citation_is_requested(token, str(item.get("uid") or ""), requested_tokens, cite_uids)
            and token not in {_reference_token(ref) for ref in references}
        ):
            references.append(reference)
    return references


def _citation_is_requested(token: str, uid: str, requested_tokens: set[str], cite_uids: list[str]) -> bool:
    """Match by evidence handle when provided, otherwise fall back to requested email UIDs."""
    return token in requested_tokens if requested_tokens else bool(uid and uid in cite_uids)


def _max_citations(decision: str, requested_references: list[dict[str, str]], cite_uids: list[str]) -> int:
    """Allow one citation for direct answers and at most two competing references for ambiguity."""
    if decision != "ambiguous":
        return 1
    requested_count = sum(bool(_reference_token(reference)) for reference in requested_references)
    return min(2, max(requested_count, len(cite_uids), 1))


def _confidence_phrase(decision: str, confidence_label: str) -> str:
    """Choose calibrated claim wording that never overstates non-answer decisions."""
    if decision != "answer":
        return "The available evidence is limited"
    return "The evidence strongly indicates" if confidence_label == "high" else "The available evidence suggests"


def _final_answer_contract(*, answer_policy: dict[str, Any]) -> dict[str, Any]:
    """Return the outward response contract for mailbox answers."""
    decision = str(answer_policy.get("decision") or "insufficient_evidence")
    citation_references = _citation_reference_payloads(answer_policy.get("cite_candidate_references"))
    return {
        "decision": decision,
        "answer_format": _answer_format(answer_policy, decision),
        "citation_format": _citation_format(),
        "confidence_wording": str(answer_policy.get("confidence_phrase") or ""),
        "ambiguity_wording": str(answer_policy.get("ambiguity_phrase") or ""),
        "fallback_wording": str(answer_policy.get("fallback_phrase") or ""),
        "required_citation_uids": _string_values(answer_policy.get("cite_candidate_uids")),
        "required_citation_handles": _citation_handles(citation_references),
        "required_citation_references": citation_references,
        "verification_mode": str(answer_policy.get("verification_mode") or ""),
        "exact_wording_requested": bool(answer_policy.get("exact_wording_requested")),
        "refuse_to_overclaim": bool(answer_policy.get("refuse_to_overclaim", True)),
    }


def _answer_format(policy: dict[str, Any], decision: str) -> dict[str, Any]:
    """Describe paragraph shape, citation placement, and wording requirements for the decision state."""
    return {
        "shape": "two_short_paragraphs" if decision == "ambiguous" else "single_paragraph",
        "cite_at_sentence_end": True,
        "max_citations": int(policy.get("max_citations") or 0),
        "include_confidence_wording": decision == "answer",
        "include_ambiguity_wording": decision == "ambiguous",
        "include_fallback_wording": decision == "insufficient_evidence",
    }


def _citation_format() -> dict[str, str]:
    """Declare the only accepted inline evidence-handle and UID citation syntax."""
    return {
        "style": "inline_reference_brackets",
        "pattern": "[ref:<EVIDENCE_HANDLE>] or [uid:<EMAIL_UID>] when no evidence handle is available",
        "required_attribution": "Only cite references from required_citation_handles or required_citation_uids.",
    }


def _string_values(values: Any) -> list[str]:
    """Discard empty values while normalizing remaining citation fields to strings."""
    return [str(value) for value in values or [] if value]


def _citation_handles(references: list[dict[str, str]]) -> list[str]:
    """Extract non-empty evidence handles in reference order."""
    return [str(reference.get("evidence_handle") or "") for reference in references if reference.get("evidence_handle")]


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
        return _dated_description(f'the chat record "{subject or item.get("source_id") or "chat record"}"', date)
    if source_type in {"formal_document", "note_record", "time_record", "participation_record", "meeting_note"}:
        return _dated_description(f'the {source_type.replace("_", " ")} "{subject or item.get("source_id") or "record"}"', date)
    if isinstance(attachment, dict):
        filename = str(attachment.get("filename") or "attachment").strip()
        base = f'the attachment "{filename}"'
        if subject:
            base += f' in "{subject}"'
    else:
        base = f'the message "{subject}"' if subject else "the strongest matching message"
    return _dated_description(base, date)


def _dated_description(base: str, date: str) -> str:
    """Append an ISO calendar date to an evidence description when available."""
    return f"{base} from {date[:10]}" if date else base


def _exact_excerpt(item: dict[str, Any]) -> str:
    """Collapse whitespace, cap excerpts at 240 characters, and quote the verified wording."""
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
    """Render answer text, decision, and citations from the selected evidence bundle."""
    ordered = _ordered_evidence(candidates, attachment_candidates)
    decision = str(answer_policy.get("decision") or final_answer_contract.get("decision") or "insufficient_evidence")
    citation_references = _contract_citation_references(final_answer_contract)
    citation_text = " ".join(_citation_token(reference) for reference in citation_references)
    exact_wording_requested = bool(
        final_answer_contract.get("exact_wording_requested") or answer_policy.get("exact_wording_requested")
    )
    text = _final_answer_text(
        decision, ordered, answer_policy, final_answer_contract, citation_text, exact_wording_requested, citation_references
    )
    return _rendered_answer_payload(decision, text, citation_references, answer_policy, final_answer_contract)


def _contract_citation_references(final_answer_contract: dict[str, Any]) -> list[dict[str, str]]:
    """Prefer structured contract references and reconstruct them from legacy UID/handle lists."""
    references = _citation_reference_payloads(final_answer_contract.get("required_citation_references"))
    if references:
        return references
    uids = [str(uid) for uid in final_answer_contract.get("required_citation_uids", []) if uid]
    handles = [str(handle) for handle in final_answer_contract.get("required_citation_handles", []) if handle]
    return [{"uid": uid, "evidence_handle": handles[index] if index < len(handles) else ""} for index, uid in enumerate(uids)]


def _final_answer_text(
    decision: str,
    ordered: list[dict[str, Any]],
    answer_policy: dict[str, Any],
    final_answer_contract: dict[str, Any],
    citation_text: str,
    exact_wording_requested: bool,
    references: list[dict[str, str]],
) -> str:
    """Render answer text in the response format consumed by callers."""
    if decision == "ambiguous":
        return _ambiguous_answer_text(ordered, answer_policy, final_answer_contract, citation_text, references)
    if decision == "answer":
        return _supported_answer_text(
            ordered[0] if ordered else None, answer_policy, final_answer_contract, citation_text, exact_wording_requested
        )
    return _insufficient_answer_text(ordered[0] if ordered else None, answer_policy, final_answer_contract, citation_text)


def _ambiguous_answer_text(
    ordered: list[dict[str, Any]],
    answer_policy: dict[str, Any],
    contract: dict[str, Any],
    citation_text: str,
    references: list[dict[str, str]],
) -> str:
    """Describe up to two supported alternatives using contract wording and their required citations."""
    tokens = {_reference_token(reference) for reference in references if _reference_token(reference)}
    descriptions = [_evidence_description(item) for item in ordered if _reference_token(_citation_reference(item)) in tokens][:2]
    first = str(
        contract.get("ambiguity_wording") or answer_policy.get("ambiguity_phrase") or "The available evidence is ambiguous."
    )
    first = first if first.endswith(".") else f"{first}."
    second = (
        "The strongest candidates are " + " and ".join(descriptions) + "."
        if descriptions
        else "The strongest candidates remain too close to support one confident answer."
    )
    return f"{first}\n\n{second}{f' {citation_text}' if citation_text else ''}"


def _supported_answer_text(
    item: dict[str, Any] | None, policy: dict[str, Any], contract: dict[str, Any], citation_text: str, exact_requested: bool
) -> str:
    """Render a supported claim, using exact quoted wording only when verification permits it."""
    if item is None:
        return "No answer-bearing evidence is available."
    prefix = str(
        contract.get("confidence_wording") or policy.get("confidence_phrase") or "The available evidence suggests"
    ).strip()
    excerpt = _exact_excerpt(item)
    verified = str(item.get("verification_status") or "") in _EXACT_VERIFICATION_STATUSES
    sentence = (
        f"{prefix} the exact wording is {excerpt}."
        if exact_requested and excerpt and verified
        else f"{prefix} {_evidence_description(item)}."
    )
    return f"{sentence} {citation_text}".strip()


def _insufficient_answer_text(
    item: dict[str, Any] | None, policy: dict[str, Any], contract: dict[str, Any], citation_text: str
) -> str:
    """Render fail-closed fallback wording and identify the strongest candidate without asserting content."""
    fallback = (
        str(contract.get("fallback_wording") or policy.get("fallback_phrase") or "").strip()
        or "I can identify the likely message, but the available evidence is too weak to state the content confidently."
    )
    if item is None:
        return fallback
    text = f"{fallback} The strongest candidate is {_evidence_description(item)}."
    return f"{text} {citation_text}" if citation_text else text


def _rendered_answer_payload(
    decision: str, text: str, references: list[dict[str, str]], policy: dict[str, Any], contract: dict[str, Any]
) -> dict[str, Any]:
    """Package answer text, decision metadata, and citations into the public response payload."""
    return {
        "decision": decision,
        "text": text.strip(),
        "citations": [str(reference.get("evidence_handle") or reference.get("uid") or "") for reference in references],
        "verification_mode": str(contract.get("verification_mode") or policy.get("verification_mode") or ""),
        "answer_shape": str((contract.get("answer_format") or {}).get("shape") or ""),
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
    transitions = {"sender": 0, "thread": 0, "recipients": 0}
    previous = {"sender": "", "thread": "", "recipients": ""}
    for index, item in enumerate(ordered, start=1):
        event, current = _timeline_event(index, item, previous)
        _count_timeline_transitions(event, transitions)
        events.append(event)
        previous = {key: value or previous[key] for key, value in current.items()}
    if not events:
        return _empty_timeline_summary()
    return _populated_timeline_summary(events, transitions)


def _timeline_event(index: int, item: dict[str, Any], previous: dict[str, str]) -> tuple[dict[str, Any], dict[str, str]]:
    """Compare one ranked item with prior sender, thread, and recipient state to mark transitions."""
    recipients_summary: dict[str, Any] = as_dict(item.get("recipients_summary"))
    current = _timeline_current_values(item, recipients_summary)
    changed = {key: bool(index > 1 and value and previous[key] and value != previous[key]) for key, value in current.items()}
    return _timeline_event_payload(index, item, recipients_summary, changed), current


def _timeline_current_values(item: dict[str, Any], recipients_summary: dict[str, Any]) -> dict[str, str]:
    """Extract normalized sender, thread, and recipient signatures for transition comparison."""
    return {
        "sender": _first_text(item, "sender_actor_id", "sender_email"),
        "thread": _first_text(item, "thread_group_id", "conversation_id"),
        "recipients": str(recipients_summary.get("signature") or ""),
    }


def _first_text(item: dict[str, Any], primary: str, fallback: str) -> str:
    """Prefer a canonical field and use its fallback only when the primary value is empty."""
    return str(item.get(primary) or item.get(fallback) or "")


def _timeline_event_payload(
    index: int, item: dict[str, Any], recipients_summary: dict[str, Any], changed: dict[str, bool]
) -> dict[str, Any]:
    """Attach transition flags and recipient context to the stable timeline event fields."""
    return {
        **_timeline_item_fields(index, item),
        "recipients_summary": recipients_summary,
        "sender_changed_from_previous": changed["sender"],
        "thread_changed_from_previous": changed["thread"],
        "recipient_set_changed_from_previous": changed["recipients"],
    }


def _timeline_item_fields(index: int, item: dict[str, Any]) -> dict[str, Any]:
    """Project ranked evidence onto the stable timeline event schema."""
    return {
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
    }


def _count_timeline_transitions(event: dict[str, Any], transitions: dict[str, int]) -> None:
    """Calculate timeline transitions for bounded response decisions."""
    transitions["sender"] += int(bool(event["sender_changed_from_previous"]))
    transitions["thread"] += int(bool(event["thread_changed_from_previous"]))
    transitions["recipients"] += int(bool(event["recipient_set_changed_from_previous"]))


def _empty_timeline_summary() -> dict[str, Any]:
    """Return the zero-event timeline contract with empty identities and transition counts."""
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


def _populated_timeline_summary(events: list[dict[str, Any]], transitions: dict[str, int]) -> dict[str, Any]:
    """Combine timeline identity statistics, transition counts, and ordered events."""
    first, last = events[0], events[-1]
    return {
        **_timeline_summary_identity(events, first, last),
        "sender_change_count": transitions["sender"],
        "thread_change_count": transitions["thread"],
        "recipient_set_change_count": transitions["recipients"],
        "events": events,
    }


def _timeline_summary_identity(events: list[dict[str, Any]], first: dict[str, Any], last: dict[str, Any]) -> dict[str, Any]:
    """Calculate date bounds, endpoint UIDs, strongest transition, and unique actor/thread counts."""
    return {
        "event_count": len(events),
        "date_range": {"first": str(first.get("date") or "")[:10], "last": str(last.get("date") or "")[:10]},
        "first_uid": first["uid"],
        "last_uid": last["uid"],
        "key_transition_uid": str(max(events, key=lambda event: float(event.get("score") or 0.0)).get("uid") or ""),
        "unique_sender_count": len(
            {
                _first_text(event, "sender_actor_id", "sender_email")
                for event in events
                if _first_text(event, "sender_actor_id", "sender_email")
            }
        ),
        "unique_thread_group_count": len(
            {
                _first_text(event, "thread_group_id", "conversation_id")
                for event in events
                if _first_text(event, "thread_group_id", "conversation_id")
            }
        ),
    }
