"""Answer-context helpers extracted from ``src.tools.search``."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, cast

from ..language_rhetoric import LANGUAGE_RHETORIC_VERSION, analyze_message_rhetoric
from ..message_behavior import (
    MESSAGE_BEHAVIOR_VERSION,
    analyze_message_behavior,
    inject_reply_pairing_findings,
    normalize_message_findings_payload,
)
from ..reply_context import extract_reply_context
from ..reply_pairing import build_reply_pairing_index
from .search_answer_context_case_payloads import (
    _apply_actor_ids_to_candidates,
    _apply_actor_ids_to_case_bundle,
    _compact_actor_identity_graph_payload,
    _compact_case_bundle_payload,
    _compact_case_patterns_payload,
    _compact_comparative_treatment_payload,
    _compact_language_rhetoric_payload,
    _compact_message_findings_payload,
    _quote_attribution_metrics,
)
from .search_answer_context_evidence import (
    _answer_context_search_kwargs,
    _as_dict,
    _attach_conversation_context,
    _attachment_candidate,
    _attachment_evidence_profile,
    _compact_optional_case_surfaces,
    _compact_retaliation_analysis_payload,
    _conversation_group_summaries,
    _is_attachment_result,
    _match_reason,
    _provenance_for_candidate,
    _public_retrieval_diagnostics,
    _recipients_summary,
    _retrieval_diagnostics,
    _snippet,
    _thread_graph_for_email,
    _thread_locator_for_candidate,
)

if TYPE_CHECKING:
    from ..message_behavior import MessageBehaviorAnalysis

_EMAIL_CANDIDATE_RE = re.compile(r"(?i)(?:mailto:)?([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})")
_FROM_HEADER_RE = re.compile(r"(?im)^from:\s*(.+)$")

__all__ = [
    "_answer_context_search_kwargs",
    "_apply_actor_ids_to_candidates",
    "_apply_actor_ids_to_case_bundle",
    "_apply_reply_pairings_to_candidates",
    "_as_dict",
    "_attach_conversation_context",
    "_attachment_candidate",
    "_attachment_evidence_profile",
    "_compact_actor_identity_graph_payload",
    "_compact_case_bundle_payload",
    "_compact_case_patterns_payload",
    "_compact_comparative_treatment_payload",
    "_compact_language_rhetoric_payload",
    "_compact_message_findings_payload",
    "_compact_optional_case_surfaces",
    "_compact_retaliation_analysis_payload",
    "_conversation_group_summaries",
    "_infer_quoted_speaker",
    "_is_attachment_result",
    "_language_rhetoric_for_candidate",
    "_match_reason",
    "_message_findings_for_candidate",
    "_provenance_for_candidate",
    "_public_retrieval_diagnostics",
    "_quote_attribution_metrics",
    "_recipients_summary",
    "_retrieval_diagnostics",
    "_segment_rows_for_uid",
    "_snippet",
    "_speaker_attribution_for_candidate",
    "_thread_graph_for_email",
    "_thread_locator_for_candidate",
    "build_answer_context",
]


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
        _normalize_attributed_email(identity) for identity in ((full_email or {}).get("reply_context_to") or []) if identity
    ]
    identities = [
        identity for identity in [reply_context_from, *reply_context_to] if identity and identity != normalized_authored_email
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
    if reply_context_from and not quoted_block_emails and not quoted_reply_context_identities:
        return {
            "speaker_email": reply_context_from,
            "source": "reply_context_from",
            "confidence": 0.8,
            "quote_attribution_status": "reply_context_fallback",
            "quote_attribution_reason": (
                "Quoted ownership is inferred from the visible reply context because "
                "the quoted block has no explicit identity markers."
            ),
            "candidate_emails": [reply_context_from],
            "downgraded_due_to_quote_ambiguity": True,
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
                "downgraded_due_to_quote_ambiguity": bool(quote_attribution.get("downgraded_due_to_quote_ambiguity", True)),
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
                    "downgraded_due_to_quote_ambiguity": bool(block.get("downgraded_due_to_quote_ambiguity", True)),
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
        str(value).strip().lower() for field in ("to", "cc", "bcc") for value in ((full_email or {}).get(field) or []) if value
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
    quoted_candidate_count = sum(int(block["findings"]["behavior_candidate_count"]) for block in quoted_block_findings)
    return normalize_message_findings_payload(
        {
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
    )


def _apply_reply_pairings_to_candidates(
    *,
    candidates: list[dict[str, Any]],
    full_map: dict[str, Any],
    case_scope: Any,
) -> None:
    """Annotate candidates with reply-pairing metadata and derived message findings."""
    reply_pairing_index = build_reply_pairing_index(
        candidates=candidates,
        full_map=full_map if isinstance(full_map, dict) else {},
        case_scope=case_scope,
    )
    for candidate in candidates:
        uid = str(candidate.get("uid") or "")
        reply_pairing = reply_pairing_index.get(uid)
        if not isinstance(reply_pairing, dict):
            continue
        message_findings = normalize_message_findings_payload(_as_dict(candidate.get("message_findings")))
        candidate["message_findings"] = message_findings
        authored = message_findings.get("authored_text")
        message_findings["authored_text"] = inject_reply_pairing_findings(
            cast("MessageBehaviorAnalysis", authored),
            reply_pairing=reply_pairing,
        )
        summary = dict(message_findings.get("summary") or {})
        summary["authored_behavior_candidate_count"] = int(message_findings["authored_text"].get("behavior_candidate_count") or 0)
        summary["total_behavior_candidate_count"] = summary["authored_behavior_candidate_count"] + int(
            summary.get("quoted_behavior_candidate_count") or 0
        )
        message_findings["summary"] = summary
        candidate["message_findings"] = normalize_message_findings_payload(message_findings)
        candidate["reply_pairing"] = {
            "request_expected": bool(reply_pairing.get("request_expected")),
            "target_authored_request": bool(reply_pairing.get("target_authored_request")),
            "response_status": str(reply_pairing.get("response_status") or ""),
            "response_delay_hours": reply_pairing.get("response_delay_hours"),
            "supports_selective_non_response_inference": bool(reply_pairing.get("supports_selective_non_response_inference")),
        }


async def build_answer_context(deps: Any, params: Any) -> str:
    """Build the answer-context payload for ``email_answer_context``."""
    from .search_answer_context_runtime import build_answer_context as _build_answer_context

    return await _build_answer_context(deps, params)
