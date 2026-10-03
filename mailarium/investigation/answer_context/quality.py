"""Evidence strength, rank ordering, answer quality, and citation references."""

from __future__ import annotations

from typing import Any


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
    ordered = _ordered_evidence(candidates, attachment_candidates)
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


def _ordered_evidence(
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return answer evidence ordered by score descending."""
    return sorted([*candidates, *attachment_candidates], key=_evidence_rank_key, reverse=True)
