"""Typed persistence stages for one evidence-harvest wave."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._utils import _compact


@dataclass(slots=True)
class HarvestWaveRequest:
    """Stable request values shared by candidate persistence stages."""

    db: Any
    run_id: str
    phase_id: str
    promote_limit: int
    meta: dict[str, Any]


@dataclass(slots=True)
class HarvestWaveCounters:
    """Mutable counters accumulated in candidate input order."""

    candidate_count: int = 0
    body_candidate_count: int = 0
    attachment_candidate_count: int = 0
    exact_body_candidate_count: int = 0
    duplicate_candidate_count: int = 0
    promoted_count: int = 0
    linked_existing_evidence_count: int = 0
    promoted_evidence_ids: list[int] = field(default_factory=list)


def harvest_wave_stage(
    db: Any,
    *,
    payload: dict[str, Any],
    run_id: str,
    phase_id: str,
    harvest_limit_per_wave: int,
    promote_limit_per_wave: int,
) -> dict[str, Any]:
    """Persist candidates and promote verified quotes in their original order."""
    from .evidence_harvest import _candidate_rows, _wave_meta

    meta = _wave_meta(payload)
    request = HarvestWaveRequest(db, run_id, phase_id, promote_limit_per_wave, meta)
    counters = HarvestWaveCounters()
    for candidate_kind, candidate in _candidate_rows(payload, harvest_limit_per_wave=harvest_limit_per_wave):
        _process_candidate(request, counters, candidate_kind, candidate)
    return _completed_payload(request, counters)


def _process_candidate(
    request: HarvestWaveRequest,
    counters: HarvestWaveCounters,
    candidate_kind: str,
    candidate: dict[str, Any],
) -> None:
    from .evidence_harvest import _recover_exact_quote

    recovered = _recover_exact_quote(request.db, candidate_kind=candidate_kind, candidate=candidate)
    quote = recovered or _compact(candidate.get("snippet"))
    if not quote:
        return
    _count_candidate_kind(counters, candidate_kind, bool(recovered))
    stored = _store_candidate(request, candidate_kind, candidate, quote, bool(recovered))
    if not stored.get("inserted"):
        counters.duplicate_candidate_count += 1
        return
    counters.candidate_count += 1
    if recovered and counters.promoted_count < request.promote_limit:
        _promote_candidate(request, counters, stored, candidate_kind, candidate, quote)


def _count_candidate_kind(counters: HarvestWaveCounters, candidate_kind: str, verified: bool) -> None:
    if candidate_kind == "body":
        counters.body_candidate_count += 1
        counters.exact_body_candidate_count += int(verified)
    else:
        counters.attachment_candidate_count += 1


def _store_candidate(
    request: HarvestWaveRequest,
    candidate_kind: str,
    candidate: dict[str, Any],
    quote: str,
    verified: bool,
) -> dict[str, Any]:
    from .evidence_harvest import _as_dict, _as_list, _candidate_context, _candidate_summary

    meta = request.meta
    return request.db.add_evidence_candidate(
        run_id=request.run_id,
        phase_id=request.phase_id,
        wave_id=meta["wave_id"],
        wave_label=meta["wave_label"],
        question_ids=meta["question_ids"],
        email_uid=_compact(candidate.get("uid")) or None,
        candidate_kind=candidate_kind,
        quote_candidate=quote,
        summary=_candidate_summary(
            wave_label=meta["wave_label"],
            question_ids=meta["question_ids"],
            candidate_kind=candidate_kind,
            rank=int(candidate.get("rank") or 0),
        ),
        category_hint="general",
        rank=int(candidate.get("rank") or 0),
        score=float(candidate.get("score") or 0.0),
        verification_status=_compact(candidate.get("verification_status")),
        verified_exact=verified,
        subject=_compact(candidate.get("subject")),
        sender_name=_compact(candidate.get("sender_name")),
        sender_email=_compact(candidate.get("sender_email")),
        date=_compact(candidate.get("date")),
        conversation_id=_compact(candidate.get("conversation_id")),
        matched_query_lanes=[_compact(item) for item in _as_list(candidate.get("matched_query_lanes")) if _compact(item)],
        matched_query_queries=[_compact(item) for item in _as_list(candidate.get("matched_query_queries")) if _compact(item)],
        provenance=_as_dict(candidate.get("provenance")),
        context=_candidate_context(
            candidate=candidate,
            candidate_kind=candidate_kind,
            wave_id=meta["wave_id"],
            question_ids=meta["question_ids"],
            scan_id=meta["scan_id"],
        ),
    )


def _promote_candidate(
    request: HarvestWaveRequest,
    counters: HarvestWaveCounters,
    stored: dict[str, Any],
    candidate_kind: str,
    candidate: dict[str, Any],
    quote: str,
) -> None:
    from .evidence_harvest import _document_locator_for_candidate

    email_uid = _compact(candidate.get("uid"))
    if not email_uid:
        return
    locator = _document_locator_for_candidate(candidate_kind=candidate_kind, candidate=candidate)
    existing = _existing_evidence(request.db, email_uid, quote, candidate_kind, locator)
    if existing:
        _link_existing(request.db, counters, stored, existing)
        return
    evidence = _add_evidence(request, candidate_kind, candidate, email_uid, quote, locator)
    _mark_promoted(request.db, counters, stored, evidence)


def _existing_evidence(db: Any, email_uid: str, quote: str, candidate_kind: str, locator: dict[str, Any]) -> Any:
    finder = getattr(db, "find_evidence_by_email_artifact_quote", None)
    if callable(finder):
        return finder(email_uid=email_uid, key_quote=quote, candidate_kind=candidate_kind, document_locator=locator)
    return db.find_evidence_by_email_quote(email_uid=email_uid, key_quote=quote)


def _link_existing(db: Any, counters: HarvestWaveCounters, stored: dict[str, Any], existing: Any) -> None:
    from .evidence_harvest import _as_dict

    stored_id, existing_id = int(_as_dict(stored).get("id") or 0), int(_as_dict(existing).get("id") or 0)
    if stored_id and existing_id:
        db.mark_evidence_candidate_promoted(stored_id, evidence_id=existing_id)
    counters.linked_existing_evidence_count += 1


def _add_evidence(
    request: HarvestWaveRequest,
    candidate_kind: str,
    candidate: dict[str, Any],
    email_uid: str,
    quote: str,
    locator: dict[str, Any],
) -> Any:
    from .evidence_harvest import (
        _as_dict,
        _candidate_context,
        _notes_for_promoted_candidate,
        _relevance_for_candidate,
    )

    meta = request.meta
    return request.db.add_evidence(
        email_uid=email_uid,
        category="general",
        key_quote=quote,
        summary=f"{meta['wave_label']}: auto-promoted exact quote from archive harvest.",
        relevance=_relevance_for_candidate(rank=int(candidate.get("rank") or 0)),
        notes=_notes_for_promoted_candidate(
            run_id=request.run_id,
            phase_id=request.phase_id,
            wave_id=meta["wave_id"],
            question_ids=meta["question_ids"],
            candidate=candidate,
        ),
        candidate_kind=candidate_kind,
        provenance=_as_dict(candidate.get("provenance")),
        document_locator=locator,
        context=_candidate_context(
            candidate=candidate,
            candidate_kind=candidate_kind,
            wave_id=meta["wave_id"],
            question_ids=meta["question_ids"],
            scan_id=meta["scan_id"],
        ),
    )


def _mark_promoted(db: Any, counters: HarvestWaveCounters, stored: dict[str, Any], evidence: Any) -> None:
    from .evidence_harvest import _as_dict

    stored_id, evidence_id = int(_as_dict(stored).get("id") or 0), int(_as_dict(evidence).get("id") or 0)
    if not stored_id or not evidence_id:
        return
    db.mark_evidence_candidate_promoted(stored_id, evidence_id=evidence_id)
    counters.promoted_count += 1
    counters.promoted_evidence_ids.append(evidence_id)


def _completed_payload(request: HarvestWaveRequest, counters: HarvestWaveCounters) -> dict[str, Any]:
    return {
        "status": "completed",
        "run_id": request.run_id,
        "phase_id": request.phase_id,
        "wave_id": request.meta["wave_id"],
        "wave_label": request.meta["wave_label"],
        "question_ids": list(request.meta["question_ids"]),
        "candidate_count": counters.candidate_count,
        "body_candidate_count": counters.body_candidate_count,
        "attachment_candidate_count": counters.attachment_candidate_count,
        "exact_body_candidate_count": counters.exact_body_candidate_count,
        "duplicate_candidate_count": counters.duplicate_candidate_count,
        "promoted_count": counters.promoted_count,
        "linked_existing_evidence_count": counters.linked_existing_evidence_count,
        "promoted_evidence_ids": counters.promoted_evidence_ids,
    }
