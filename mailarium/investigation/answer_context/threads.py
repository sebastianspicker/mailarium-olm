"""Recipient summaries, thread graph fields, and conversation-group context for candidates."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .text import _text

if TYPE_CHECKING:
    from mailarium.archive import ArchiveDatabase


def _recipients_summary(full_email: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact visible-recipient summary for chronology and appendix views."""
    if not isinstance(full_email, dict):
        return {"status": "not_available"}

    visible_recipients: list[str] = []
    counts = {"to": 0, "cc": 0, "bcc": 0}
    for field in ("to", "cc", "bcc"):
        field_values = [str(value).strip().lower() for value in (full_email.get(field) or []) if value]
        counts[field] = len(field_values)
        for value in field_values:
            if value and value not in visible_recipients:
                visible_recipients.append(value)

    if not visible_recipients:
        return {
            "status": "empty",
            "to_count": counts["to"],
            "cc_count": counts["cc"],
            "bcc_count": counts["bcc"],
            "visible_recipient_count": 0,
            "visible_recipient_emails": [],
            "signature": "",
        }

    return {
        "status": "available",
        "to_count": counts["to"],
        "cc_count": counts["cc"],
        "bcc_count": counts["bcc"],
        "visible_recipient_count": len(visible_recipients),
        "visible_recipient_emails": visible_recipients,
        "signature": "|".join(visible_recipients),
    }


def _references_for_email(full_email: dict[str, Any] | None) -> list[str]:
    """Read message references from structured data or legacy JSON without propagating malformed values."""
    if not full_email:
        return []
    raw = full_email.get("references") or []
    if not raw and full_email.get("references_json"):
        import json

        try:
            raw = json.loads(str(full_email.get("references_json") or "[]"))
        except json.JSONDecodeError:
            raw = []
    return [str(item) for item in raw if item] if isinstance(raw, list) else []


def _thread_graph_for_email(
    full_email: dict[str, Any] | None,
    *,
    fallback_conversation_id: str = "",
) -> dict[str, Any] | None:
    """Return canonical vs inferred thread graph fields for one email."""
    if not full_email and not fallback_conversation_id:
        return None
    email = full_email or {}
    references = _references_for_email(full_email)
    conversation_id = _text(email.get("conversation_id") or fallback_conversation_id)
    in_reply_to = _text(email.get("in_reply_to"))
    canonical = {
        "conversation_id": conversation_id,
        "in_reply_to": in_reply_to,
        "references": references,
        "has_thread_links": bool(conversation_id or in_reply_to or references),
    }
    inferred = {
        "parent_uid": _text(email.get("inferred_parent_uid")),
        "thread_id": _text(email.get("inferred_thread_id")),
        "reason": _text(email.get("inferred_match_reason")),
        "confidence": float(email.get("inferred_match_confidence") or 0.0),
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


def _add_candidate_to_group(grouped: dict[str, dict[str, Any]], candidate: dict[str, Any]) -> None:
    """Accumulate a candidate under its thread group while retaining its strongest evidence."""
    group_id = str(candidate.get("thread_group_id") or "")
    if not group_id:
        return
    score = float(candidate.get("score") or 0.0)
    uid = str(candidate.get("uid") or "")
    group = grouped.setdefault(
        group_id,
        {
            "conversation_id": str(candidate.get("conversation_id") or ""),
            "inferred_thread_id": str(candidate.get("inferred_thread_id") or ""),
            "thread_group_id": group_id,
            "thread_group_source": str(candidate.get("thread_group_source") or "canonical"),
            "top_uid": uid,
            "top_score": score,
            "matched_uids": [],
            "participants": [],
            "date_range": {},
            "message_count": 0,
        },
    )
    if uid and uid not in group["matched_uids"]:
        group["matched_uids"].append(uid)
    if score > float(group["top_score"]):
        group["top_score"] = score
        group["top_uid"] = uid


def _email_rows(value: Any) -> list[dict[str, Any]]:
    """Normalize absent database results to an empty row list."""
    return value if value else []


def _thread_emails_for_group(db: ArchiveDatabase | None, group: dict[str, Any]) -> list[dict[str, Any]]:
    """Load canonical or inferred thread messages according to the group provenance."""
    if not db:
        return []
    if group["thread_group_source"] == "canonical":
        return _email_rows(db.queries.get_thread_emails(str(group["conversation_id"] or "")))
    if group["thread_group_source"] == "inferred":
        return _email_rows(db.queries.get_inferred_thread_emails(str(group["inferred_thread_id"] or "")))
    if group["conversation_id"]:
        return _email_rows(db.queries.get_thread_emails(str(group["conversation_id"] or "")))
    return []


def _finalize_group(db: ArchiveDatabase | None, group: dict[str, Any]) -> None:
    """Enrich a conversation group with participants, message count, and date range when thread rows exist."""
    emails = _thread_emails_for_group(db, group)
    if not emails:
        group["message_count"] = len(group["matched_uids"])
        return
    group["participants"] = sorted({str(email.get("sender_email") or "") for email in emails if email.get("sender_email")})
    dates = sorted(str(email.get("date") or "")[:10] for email in emails if email.get("date"))
    group["message_count"] = len(emails)
    group["date_range"] = {"first": dates[0], "last": dates[-1]} if dates else {}


def _conversation_group_summaries(
    db: ArchiveDatabase | None,
    *,
    candidates: list[dict[str, Any]],
    attachment_candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Group ranked evidence into compact conversation summaries before answer rendering."""
    grouped: dict[str, dict[str, Any]] = {}
    for candidate in [*candidates, *attachment_candidates]:
        _add_candidate_to_group(grouped, candidate)
    for group in grouped.values():
        _finalize_group(db, group)

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
