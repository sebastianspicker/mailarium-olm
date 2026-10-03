"""Exact-wording detection, answer-synthesis policy, and the final-answer contract."""

from __future__ import annotations

import re
from typing import Any

from .quality import (
    _citation_reference,
    _citation_reference_payloads,
    _is_weak_evidence_item,
    _ordered_evidence,
    _reference_token,
)
from .text import _truthy_strings

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
        "required_citation_uids": _truthy_strings(answer_policy.get("cite_candidate_uids")),
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


def _citation_handles(references: list[dict[str, str]]) -> list[str]:
    """Extract non-empty evidence handles in reference order."""
    return [str(reference.get("evidence_handle") or "") for reference in references if reference.get("evidence_handle")]
