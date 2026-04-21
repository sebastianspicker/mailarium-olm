"""Citation builders for behavioural evidence chains."""

from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    """Return one dict-valued payload or an empty dict."""
    return value if isinstance(value, dict) else {}


def _actor_block(candidate: dict[str, Any], *, quoted_speaker: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return stable actor metadata for one evidence citation."""
    quoted = quoted_speaker or {}
    actor_ids = [str(candidate.get("sender_actor_id") or "")]
    actor_emails = [str(candidate.get("sender_email") or "")]
    quoted_actor_id = str(quoted.get("speaker_actor_id") or "")
    quoted_email = str(quoted.get("speaker_email") or "")
    if quoted_actor_id:
        actor_ids.append(quoted_actor_id)
    if quoted_email:
        actor_emails.append(quoted_email)
    return {
        "actor_ids": [actor_id for actor_id in actor_ids if actor_id],
        "actor_emails": [email for email in actor_emails if email],
    }


def _base_citation(
    candidate: dict[str, Any],
    *,
    finding_id: str,
    evidence_role: str,
    excerpt: str,
    text_origin: str,
    evidence_handle: str,
    start: int | None,
    end: int | None,
    segment_ordinal: int | None = None,
    segment_type: str = "",
    quoted_speaker: dict[str, Any] | None = None,
    note: str = "",
    provenance_kind: str = "direct_text",
    inference_basis: str = "",
    evidence_chain_role: str = "",
) -> dict[str, Any]:
    """Build one stable evidence citation."""
    speaker_status = "not_applicable"
    quote_attribution_status = ""
    if text_origin == "quoted":
        source = str((quoted_speaker or {}).get("speaker_source") or "")
        quote_attribution_status = str((quoted_speaker or {}).get("quote_attribution_status") or "")
        if not source or source == "unresolved":
            speaker_status = "unresolved"
        elif source == "canonical_sender":
            speaker_status = "canonical"
        else:
            speaker_status = "inferred"
    provenance = _as_dict(candidate.get("provenance"))
    attributed_status = "authored"
    if text_origin == "quoted":
        attributed_status = (
            "inferred" if quote_attribution_status in {"inferred_single_candidate", "participant_exclusion"} else "quoted"
        )
    return {
        "citation_id": f"{finding_id}:{evidence_role}:{evidence_handle}:{segment_ordinal or 0}:{start or 0}:{end or 0}",
        "evidence_role": evidence_role,
        "message_or_document_id": str(candidate.get("uid") or candidate.get("source_id") or ""),
        "source_id": str(candidate.get("source_id") or ""),
        "timestamp": str(candidate.get("date") or ""),
        "source_type": "email",
        "title": str(candidate.get("subject") or ""),
        "actors": _actor_block(candidate, quoted_speaker=quoted_speaker),
        "text_attribution": {
            "text_origin": text_origin,
            "speaker_status": speaker_status,
            "authored_quoted_inferred_status": attributed_status,
            "quote_attribution_status": quote_attribution_status,
        },
        "passage": {
            "excerpt": excerpt,
            "bounds": {
                "start": start,
                "end": end,
                "segment_ordinal": segment_ordinal,
                "segment_type": segment_type,
            },
        },
        "provenance": {
            "evidence_handle": evidence_handle,
            "uid": str(candidate.get("uid") or ""),
            "snippet_start": provenance.get("snippet_start"),
            "snippet_end": provenance.get("snippet_end"),
            "provenance_kind": provenance_kind,
            "inference_basis": inference_basis,
            "evidence_chain_role": evidence_chain_role,
        },
        "note": note,
    }


def _authored_citations(
    *,
    finding_id: str,
    candidate: dict[str, Any],
    evidence_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return stable authored or metadata citations for one message finding."""
    provenance = _as_dict(candidate.get("provenance"))
    evidence_handle = str(provenance.get("evidence_handle") or f"email:{candidate.get('uid')}")
    citations: list[dict[str, Any]] = []
    for index, evidence in enumerate(evidence_items, start=1):
        text_origin = "authored"
        if str(evidence.get("source_scope") or "") == "message_metadata":
            text_origin = "metadata"
        citations.append(
            _base_citation(
                candidate,
                finding_id=finding_id,
                evidence_role="supporting",
                excerpt=str(evidence.get("excerpt") or ""),
                text_origin=text_origin,
                evidence_handle=f"{evidence_handle}:authored:{index}",
                start=int(evidence.get("start") or 0),
                end=int(evidence.get("end") or 0),
                note=str(evidence.get("matched_text") or ""),
                provenance_kind="message_metadata" if text_origin == "metadata" else "direct_text",
                inference_basis="message_local_metadata" if text_origin == "metadata" else "message_local_text",
            )
        )
    if citations:
        return citations
    return [
        _base_citation(
            candidate,
            finding_id=finding_id,
            evidence_role="supporting",
            excerpt=str(candidate.get("snippet") or ""),
            text_origin="authored",
            evidence_handle=evidence_handle,
            start=provenance.get("snippet_start"),
            end=provenance.get("snippet_end"),
            provenance_kind="direct_text",
            inference_basis="message_local_text",
        )
    ]


def _quoted_citations(
    *,
    finding_id: str,
    candidate: dict[str, Any],
    quoted_block: dict[str, Any],
    evidence_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return quoted citations and quote-quality metadata for one block finding."""
    provenance = _as_dict(candidate.get("provenance"))
    base_handle = str(provenance.get("evidence_handle") or f"email:{candidate.get('uid')}")
    segment_ordinal = int(quoted_block.get("segment_ordinal") or 0)
    speaker_source = str(quoted_block.get("speaker_source") or "")
    speaker_confidence = float(quoted_block.get("speaker_confidence") or 0.0)
    quoted_speaker = {
        "speaker_actor_id": str(quoted_block.get("speaker_actor_id") or ""),
        "speaker_email": str(quoted_block.get("speaker_email") or ""),
        "speaker_source": speaker_source,
        "quote_attribution_status": str(quoted_block.get("quote_attribution_status") or ""),
    }
    citations = [
        _base_citation(
            candidate,
            finding_id=finding_id,
            evidence_role="supporting",
            excerpt=str(evidence.get("excerpt") or ""),
            text_origin="quoted",
            evidence_handle=f"{base_handle}:quoted:{segment_ordinal}:{index}",
            start=int(evidence.get("start") or 0),
            end=int(evidence.get("end") or 0),
            segment_ordinal=segment_ordinal,
            segment_type=str(quoted_block.get("segment_type") or ""),
            quoted_speaker=quoted_speaker,
            note=str(evidence.get("matched_text") or ""),
            provenance_kind="quoted_text",
            inference_basis=str(quoted_speaker.get("quote_attribution_status") or "quoted_history"),
        )
        for index, evidence in enumerate(evidence_items, start=1)
    ]
    if not citations:
        citations = [
            _base_citation(
                candidate,
                finding_id=finding_id,
                evidence_role="supporting",
                excerpt=str(quoted_block.get("text") or ""),
                text_origin="quoted",
                evidence_handle=f"{base_handle}:quoted:{segment_ordinal}:0",
                start=0,
                end=0,
                segment_ordinal=segment_ordinal,
                segment_type=str(quoted_block.get("segment_type") or ""),
                quoted_speaker=quoted_speaker,
                provenance_kind="quoted_text",
                inference_basis=str(quoted_speaker.get("quote_attribution_status") or "quoted_history"),
            )
        ]
    downgraded = bool(quoted_block.get("downgraded_due_to_quote_ambiguity", True))
    reason = str(quoted_block.get("quote_attribution_reason") or "")
    if downgraded and not reason:
        reason = "Quoted-speaker attribution is inferred or unresolved, so the finding should be read more cautiously."
    return citations, {
        "downgraded_due_to_quote_ambiguity": downgraded,
        "reason": reason,
        "speaker_source": speaker_source,
        "speaker_confidence": speaker_confidence,
        "quote_attribution_status": str(quoted_block.get("quote_attribution_status") or ""),
        "candidate_emails": list(quoted_block.get("candidate_emails") or []),
    }


def _summary_citations(
    *,
    finding_id: str,
    candidate_map: dict[str, dict[str, Any]],
    uids: list[str],
    evidence_role: str,
    note: str = "",
    provenance_kind: str = "cross_message_inference",
    inference_basis: str = "summary_inference",
    text_origin: str = "authored",
) -> list[dict[str, Any]]:
    """Return candidate-level citations for one UID list."""
    citations: list[dict[str, Any]] = []
    for uid in uids:
        candidate = candidate_map.get(str(uid))
        if candidate is None:
            continue
        provenance = _as_dict(candidate.get("provenance"))
        citations.append(
            _base_citation(
                candidate,
                finding_id=finding_id,
                evidence_role=evidence_role,
                excerpt=str(candidate.get("snippet") or ""),
                text_origin=text_origin,
                evidence_handle=str(provenance.get("evidence_handle") or f"email:{uid}"),
                start=provenance.get("snippet_start"),
                end=provenance.get("snippet_end"),
                note=note,
                provenance_kind=provenance_kind,
                inference_basis=inference_basis,
                evidence_chain_role=evidence_role,
            )
        )
    return citations
