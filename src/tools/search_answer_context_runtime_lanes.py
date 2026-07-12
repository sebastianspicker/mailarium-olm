"""Query-lane derivation and segment retrieval helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..mcp_models import EmailAnswerContextInput
from .search_answer_context_rendering import _resolve_exact_wording_requested


def _text(value: Any) -> str:
    return str(value) if value else ""


def _segment_result(row: dict[str, Any], lane_id: str, lane_query: str) -> Any:
    from ..retriever_models import SearchResult

    ordinal = int(row.get("ordinal") or 0)
    return SearchResult(
        chunk_id=f"{row['uid']}__segment_{ordinal}",
        text=_text(row.get("segment_text")),
        metadata={
            "uid": _text(row.get("uid")),
            "subject": _text(row.get("subject")),
            "sender_email": _text(row.get("sender_email")),
            "sender_name": _text(row.get("sender_name")),
            "date": _text(row.get("date")),
            "conversation_id": _text(row.get("conversation_id")),
            "folder": _text(row.get("folder")),
            "has_attachments": bool(row.get("has_attachments") or row.get("attachment_count")),
            "detected_language": _text(row.get("detected_language")),
            "detected_language_confidence": _text(row.get("detected_language_confidence")),
            "segment_type": _text(row.get("segment_type")),
            "segment_ordinal": ordinal,
            "source_surface": _text(row.get("source_surface")),
            "body_render_source": f"message_segments:{_text(row.get('segment_type'))}",
            "score_kind": "segment_sql",
            "score_calibration": "synthetic",
            "result_key": f"segment:{row['uid']}:{ordinal}",
            "matched_query_lanes": [lane_id],
            "matched_query_queries": [lane_query],
        },
        distance=max(0.0, 1.0 - float(row.get("score") or 0.0)),
    )


def _segment_rows(retriever: Any, lane_query: str, limit: int) -> list[dict[str, Any]]:
    db = getattr(retriever, "email_db", None)
    if db is None or not hasattr(db, "search_message_segments"):
        return []
    try:
        return db.search_message_segments(lane_query, limit=limit)
    except Exception:  # pylint: disable=broad-exception-caught
        return []


def _segment_search_results(
    *, retriever: Any, lane_query: str, lane_id: str, limit: int, scan_id: str | None = None
) -> tuple[list[Any], dict[str, Any]]:
    """Search for message segments matching a lane query."""
    results = [_segment_result(row, lane_id, lane_query) for row in _segment_rows(retriever, lane_query, limit)]
    scan_meta: dict[str, Any] | None = None
    if scan_id and results:
        from ..scan_session import filter_seen

        results, scan_meta = filter_seen(scan_id, results)
    return results, {
        "segment_result_count": len(results),
        "segment_excluded_count": int((scan_meta or {}).get("excluded_count") or 0),
    }


def _append_lane(lanes: list[str], lane: str) -> None:
    compact = " ".join(_text(lane).split()).strip()
    if compact and all(existing.casefold() != compact.casefold() for existing in lanes):
        lanes.append(compact[:500])


def _person_bits(people: list[Any], fields: tuple[str, ...], limit: int) -> list[str]:
    bits: list[str] = []
    for person in people[:limit]:
        for field in fields:
            value = _text(getattr(person, field, "")).strip()
            if value:
                bits.append(value)
    return bits


@dataclass(frozen=True)
class _CaseLaneTerms:
    base: str
    target: list[str]
    actors: list[str]
    institutional: list[str]
    issue_tracks: list[str]
    issue_tags: list[str]
    allegations: list[str]
    triggers: list[str]
    comparators: list[str]


def _case_lane_terms(params: EmailAnswerContextInput, search_kwargs: dict[str, Any]) -> _CaseLaneTerms:
    scope = params.case_scope
    assert scope is not None
    actors = [*scope.suspected_actors[:6], *scope.comparator_actors[:4], *getattr(scope, "context_people", [])[:4]]
    tracks = [
        value
        for track in scope.employment_issue_tracks[:8]
        if _text(track).strip()
        for value in (_text(track).replace("_", " ").strip(), _text(track).strip())
        if value
    ]
    triggers = [
        " ".join(
            bit
            for bit in (
                _text(getattr(event, "date", "")).strip(),
                _text(getattr(event, "trigger_type", "")).replace("_", " ").strip(),
            )
            if bit
        ).strip()
        for event in scope.trigger_events[:4]
    ]
    return _CaseLaneTerms(
        base=" ".join(_text(search_kwargs.get("query")).split()).strip(),
        target=_person_bits([scope.target_person], ("name", "email"), 1),
        actors=_person_bits(actors, ("name", "email", "role_hint"), len(actors)),
        institutional=_person_bits(list(getattr(scope, "institutional_actors", [])), ("label", "email", "function"), 4),
        issue_tracks=tracks,
        issue_tags=[_text(item).strip() for item in scope.employment_issue_tags[:8] if _text(item).strip()],
        allegations=[_text(item).replace("_", " ").strip() for item in scope.allegation_focus[:6] if _text(item).strip()],
        triggers=triggers,
        comparators=_person_bits(list(scope.comparator_actors), ("name", "email"), 4),
    )


def _exact_scope_lanes(terms: _CaseLaneTerms) -> list[str]:
    lanes: list[str] = []
    attachments = ["attachment", "record", "calendar", "meeting note"]
    _append_lane(lanes, terms.base)
    _append_lane(lanes, " ".join([terms.base, *terms.target[:1], *terms.actors[:4], *terms.institutional[:2]]))
    if terms.triggers:
        _append_lane(
            lanes,
            " ".join(
                [*terms.target[:1], *terms.triggers[:3], *terms.actors[:2], *terms.institutional[:1], *terms.issue_tracks[:1]]
            ),
        )
    _append_lane(lanes, " ".join([*terms.target[:1], *terms.issue_tracks[:3], *terms.issue_tags[:2], *terms.allegations[:2]]))
    if terms.comparators:
        _append_lane(
            lanes, " ".join([*terms.target[:1], *terms.comparators[:4], *terms.issue_tracks[:2], *terms.allegations[:1]])
        )
    _append_lane(
        lanes, " ".join([*terms.target[:1], *attachments, *terms.institutional[:2], *terms.triggers[:1], *terms.issue_tracks[:1]])
    )
    return lanes[:8]


def _broad_scope_lanes(terms: _CaseLaneTerms) -> list[str]:
    lanes: list[str] = []
    attachments = ["attachment", "record", "calendar", "meeting note"]
    _append_lane(lanes, terms.base)
    _append_lane(
        lanes,
        " ".join(
            [
                terms.base,
                *terms.target[:1],
                *terms.actors[:4],
                *terms.institutional[:2],
                *terms.issue_tracks[:2],
                *terms.issue_tags[:2],
            ]
        ),
    )
    _append_lane(lanes, " ".join([*terms.target[:1], *terms.allegations[:3], *terms.issue_tracks[:3], *terms.issue_tags[:2]]))
    if terms.triggers:
        _append_lane(lanes, " ".join([*terms.target[:1], *terms.triggers[:3], *terms.issue_tracks[:2], *terms.allegations[:2]]))
    if terms.comparators:
        _append_lane(
            lanes, " ".join([*terms.target[:1], *terms.comparators[:4], *terms.issue_tracks[:2], *terms.allegations[:2]])
        )
    _append_lane(
        lanes,
        " ".join([*terms.target[:1], *attachments, *terms.institutional[:2], *terms.issue_tracks[:2], *terms.issue_tags[:2]]),
    )
    return lanes[:8]


def _scope_lanes(params: EmailAnswerContextInput, search_kwargs: dict[str, Any], exact: bool) -> list[str]:
    if params.case_scope is None:
        return []
    terms = _case_lane_terms(params, search_kwargs)
    return _exact_scope_lanes(terms) if exact else _broad_scope_lanes(terms)


def _expanded_query_lanes(retriever: Any, query: str, requested: bool) -> list[str]:
    expand = getattr(retriever, "_expand_query_lanes", None)
    if not requested or not callable(expand):
        return []
    expanded = expand(query, max_lanes=4)
    values = expanded if isinstance(expanded, list) else []
    return [" ".join(_text(item).split()).strip() for item in values if _text(item).strip()]


def _derive_query_lanes(*, retriever: Any, params: EmailAnswerContextInput, search_kwargs: dict[str, Any]) -> list[str]:
    """Derive deterministic query lanes from explicit, expanded, and case-scope terms."""
    explicit = [" ".join(_text(item).split()).strip() for item in params.query_lanes if _text(item).strip()]
    if explicit:
        return explicit[:8]
    query = _text(search_kwargs.get("query")).strip()
    if not query:
        return []
    requested = search_kwargs.get("_exact_wording_requested")
    exact = _resolve_exact_wording_requested(
        question=params.question,
        explicit=bool(requested) if requested is not None else getattr(params, "exact_wording_requested", None),
    )
    scope_lanes = _scope_lanes(params, search_kwargs, exact)
    expanded = _expanded_query_lanes(retriever, query, bool(search_kwargs.get("expand_query")))
    if not expanded:
        return scope_lanes[:8] if scope_lanes else [query]
    if not scope_lanes:
        return expanded
    combined: list[str] = []
    for lane in [*scope_lanes, *expanded]:
        _append_lane(combined, lane)
    return combined[:8]


__all__ = ["_derive_query_lanes", "_segment_search_results"]
