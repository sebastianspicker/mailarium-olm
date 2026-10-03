"""Chronological timeline summaries for process-style answer-context questions."""

from __future__ import annotations

from typing import Any

from mailarium.model.data_shapes import as_dict


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
