"""Final answer text rendering from the selected evidence bundle and answer contract."""

from __future__ import annotations

from typing import Any

from .quality import (
    _EXACT_VERIFICATION_STATUSES,
    _citation_reference,
    _citation_reference_payloads,
    _citation_token,
    _ordered_evidence,
    _reference_token,
)
from .text import _snippet


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
    snippet = _snippet(str(item.get("snippet") or ""), max_chars=240)
    if not snippet:
        return ""
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
